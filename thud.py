#!/usr/bin/env python2.7
from twisted.internet.protocol import Factory, ClientFactory
from twisted.protocols.basic import LineReceiver
from twisted.internet import reactor
from twisted.internet.endpoints import clientFromString
import uuid
import re
import yaml


STATE_NONE          = 0
WAITING_FOR_PASS    = 1
CONNECTING_UPSTREAM = 2
FORWARDING          = 3
class IRCProxy(LineReceiver):
    state = STATE_NONE
    upstream_queue = []
    upstream = None
    def connectionMade(self):
        print "CLIENT CONNECTED"
        self.state = WAITING_FOR_PASS
    def lineReceived(self,line):
        if self.state == FORWARDING:
            if len(self.upstream.clients) > 1 and line.startswith("USER"):
                print "NOT RESENDING %s" % line
                return
            print "FORWARDING FROM CLIENT: %s" % line
            self.upstream.sendLine(line)
        elif self.state == WAITING_FOR_PASS and line.startswith("PASS"):
            uri = line[5:]
            print "REQUESTING UPSTREAM: %s" % uri
            self.state = CONNECTING_UPSTREAM
            self.factory.attach_upstream(uri,self)
        elif self.state == CONNECTING_UPSTREAM:
            print "RECEIVED FROM CLIENT KEEPING TILL AFTER CONNECT: %s" % line
            self.upstream_queue.append(line)
    def upstream_attached(self, upstream):
        print "UPSTREAM_ATTACHED"
        self.upstream = upstream
        self.state = FORWARDING
        if len(self.upstream.clients) > 1:
            self.upstream_queue = []
        for line in self.upstream_queue:
            print "PLAYING OUT: %s" % line
            self.upstream.sendLine(line)
        self.upstream_queue = []

    def connectionLost(self, reason):
        print "CLIENT DISCONNECTED"
        # not a bad idea to notify the upstream or something
        if self.upstream:
            self.upstream.unregister_client(self)
    def shutdown(self):
        print "CLIENT TOLD TO SHUTDOWN"
        self.transport.abortConnection()
            
class UpstreamInfo(object):
    def __init__(self,config,user):
        self.config = config
        self.user = user
    def get_uri(self):
        return self.config["uri"]
    def get_nick(self):
        return self.config.get("nick",self.user.get_nick())

class UserInfo(object):
    def __init__(self, config):
        self.config = config
    def get_name(self):
        return self.config.get('name')
    def authenticate(self, password):
        raise NotImplemmented
    def get_upstreams(self):
        return {c["ref"]: UpstreamInfo(c,self) for c in self.config['upstreams']}
    def get_upstream(self, ref):
        return self.get_upstreams().get(ref,None)
    def get_nick(self):
        return self.config["nick"]


class IRCProxyFactory(Factory):
    protocol = IRCProxy
    def __init__(self):
        self.upstream_connections = {}
        self.users = {}

    def process_user_config(self, config):
        user = UserInfo(config)
        print "PROCESSING USER CONFIG FOR %s" % user.get_name()
        self.users[user.get_name()] = user
        for ref, upstreaminfo in user.get_upstreams().items():
            print "\t", ref, upstreaminfo.get_uri()
            d = self.connect_upstream(upstreaminfo)
            def __connected(upstream):
                print "UPSTREAM CONNECTED FOR %s" % upstream.config.get_uri()
                # we need to do a USER and NICK command to the server here.
                return upstream
            d.addCallback(__connected)

    def parse_uri(self, uri):
        qs = ""
        if "?" in uri:
            uri, qs = uri.split("?")
        args = {}
        if qs:
            for kv in qs.split("&"):
                key,value = kv.split("=")
                args[key] = value
        return uri, args
    def attach_upstream(self, uri, client):
        print "REQUESTED attach to upstream %s" % uri
        uri, args = self.parse_uri(uri)

        def __upstream_connected(upstream):
            print "UPSTREAM_CONNECTED, ATTACHING CLIENT!"
            upstream.register_client(client,args)
            client.upstream_attached(upstream)
            return upstream
        if uri in self.upstream_connections:
            print "ALREADY HAVE THIS UPSTREAM"
            __upstream_connected(self.upstream_connections[uri])
        else:
            d = self.connect_upstream(UpstreamInfo({"uri":uri,"args":args},None))
            d.addCallback(__upstream_connected)

    def connect_upstream(self, upstreamconfig):
        uri = upstreamconfig.get_uri()
        m = re.match("(?:(?P<proto>[a-zA-i0-9]+)://)?(?P<host>[a-zA-Z0-9.-]+)(:?P<port>[0-9]+)?/?",uri)
        parts = m.groupdict()
        protocol = parts.get("proto","irc").lower()
        host = parts.get("host")
        port = parts.get("port","6667")

        if protocol == "irc":
            epproto = "tcp"
        elif protocol == "ircs":
            epproto = "ssl"
        endpointstring = "%s:host=%s:port=%s" % (epproto,host,port)
        endpoint = clientFromString(reactor,endpointstring)
        d = endpoint.connect(IRCUpstreamConnectionFactory(uri))
        def __connected(upstream):
            print "UPSTREAM_CONNECTED!"
            upstream.config = upstreamconfig
            self.upstream_connections[uri] = upstream
            return upstream
        d.addCallback(__connected)
        return d



class IRCUpstreamConnection(LineReceiver):
    def __init__(self,uri):
        self.uri = uri
        self.clients = {}
        self.queue = []
    def register_client(self, client, args):
        if "resource" in args:
            resource = args[resource]
        else:
            # use a random resource identifier
            resource = uuid.uuid4().hex
        if resource in self.clients:
            # uh oh. This resource is already registered.
            self.clients[resource].shutdown()
        print "REGISTERING CLIENT WITH RESOURCE %s" % resource
        self.clients[resource] = client
        client.resource = resource
        for line in self.queue:
            print "REPLAYING TO CLIENT: %s" % line
            client.sendLine(line)

    def unregister_client(self, client):
        if client.resource in self.clients:
            del self.clients[client.resource]

    def lineReceived(self,line):
        print "FORWARDING TO CLIENTS: %s" % line
        code = line.split(" ")[1]
        if code in ["000","001","002","003","004","005","353","366","324","329","352","315","JOIN"]:
            self.queue.append(line)
        for client in self.clients.values():
            client.sendLine(line)

    def connectionLost(self, reason):
        print "UPSTREAM DISCONNECTED"
        # We should probably use a ReconnectingClientProtocol or something
        
class IRCUpstreamConnectionFactory(Factory):
    def __init__(self, uri):
        self.uri = uri
    def buildProtocol(self, addr):
        return IRCUpstreamConnection(self.uri)

if __name__ == '__main__':
    import glob
    proxyfactory = IRCProxyFactory()
    #TODO: read each .user file. For each upstream, 
    # call proxyfactory.attach_upstream(uri)
    # NOTE: we probably need to change uri to be an object 
    # containing upstream config and linking it to the user.
    for user_file in glob.glob("*.user"):
        with open(user_file,'rt') as f:
            proxyfactory.process_user_config(yaml.load(f.read()))
    reactor.listenTCP(1234,proxyfactory)
    reactor.run()
