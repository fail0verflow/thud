#!/usr/bin/env python2.7
from twisted.internet.protocol import Factory, ClientFactory
from twisted.protocols.basic import LineReceiver
from twisted.internet import reactor
from twisted.internet.endpoints import clientFromString
import re
import yaml
import glob

CALLBACK_MESSAGE        = 0
CALLBACK_DISCONNECTED   = 1
class CallBackLineReceiver(LineReceiver):
    def __init__(self):
        self.callbacks = { CALLBACK_MESSAGE: [], CALLBACK_DISCONNECTED: [] }
    def lineReceived(self,line):
        for cb in self.callbacks[CALLBACK_MESSAGE]:
            cb(self,line)
    def connectionLost(self,line):
        for cb in self.callbacks[CALLBACK_DISCONNECTED]:
            cb(self)
    def register_callback(self, kind, callback):
        if not callback in self.callbacks[kind]:
            self.callbacks[kind].append(callback)
    def unregister_callback(self, kind, callback):
        if callback in self.callbacks[kind]:
            self.callbacks[kind].remove(callback)
class UpstreamConfig(object):
    def __init__(self,config,user):
        self.config = config
        self.user = user
    def get_uri(self):
        return self.config["uri"]
    def get_ref(self):
        return self.config["ref"]
    def get_nick(self):
        return self.config.get("nick",self.user.get_nick())
    def get_realname(self):
        return self.config.get("realname",self.user.get_realname())
    def get_autoconnect(self):
        return self.config.get("autoconnect",False)

class AuthenticationFailed(Exception):
    pass
class NoSuchUpstream(Exception):
    pass

class User(object):
    """ This is the central class in thud. A User instance acts as a central point for all clients and upstream connections. All messages pass through here. """
    def __init__(self, bouncer, configfile):
        self.bouncer = bouncer
        self.configfile = configfile
        with open(self.configfile,'rt') as f:
            self.config = yaml.load(f.read())
        self.upstream_connections = {} #key is ref
        self.clients = {} # key is resource

    def save_config(self):
        with open(self.configfile,'wt') as f:
            f.write(yaml.dump(config))
    def get_name(self):
        return self.config.get('name').lower()
    def get_realname(self):
        return self.config.get('realname',self.get_name())
    def get_upstream_configs(self):
        return {c["ref"].lower(): UpstreamConfig(c,self) for c in self.config['upstreams']}
    def get_upstream_config(self, ref):
        return self.get_upstream_configs().get(ref,None)
    def get_nick(self):
        return self.config["nick"]
    def get_realname(self):
        return self.config.get("realname",self.get_name())

    def authenticate_client(self, password):
        """ Called when a downstream client connects and is attempting to authenticate """
        return 1

    def upstream_connected(self, upstream):
        """ Called when one of the upstream connections has successfully connected to the upstream server """
        print "[%s] UPSTREAM CONNECTED FOR %s" % (self.get_name(),upstream.config.get_uri())
        self.upstream_connections[upstream.config.get_ref()] = upstream
        upstream.register_callback(CALLBACK_MESSAGE, self.upstream_message)
        upstream.register_callback(CALLBACK_DISCONNECTED, self.upstream_disconnected)
        # we need to do a USER and NICK command to the server here.
        self.upstream_send(upstream,"NICK %s" % upstream.config.get_nick())
        self.upstream_send(upstream,"USER %s 0 * :%s" % (upstream.config.get_nick(), upstream.config.get_realname()))
        return upstream
    def upstream_send(self, upstream, line):
        """ Convenience function used to send messages to an upstream server """
        print "[%s][%s] UPSTREAM_SEND: %s" % (self.get_name(),upstream.config.get_uri(),line)
        upstream.sendLine(line)
    def upstream_message(self, upstream, line):
        """ Called when a message is received from an upstream connection. This message will usually be delivered to all clients, and may also be cached."""
        print "[%s][%s] UPSTREAM_RECV: %s" % (self.get_name(),upstream.config.get_uri(),line)
        for resource,client in self.clients.items():
            if client.upstreamref == upstream.config.get_ref():
                client.sendLine(line)

    def upstream_disconnected(self, upstream):
        """ Called when one of the upstream connections disconnects for whatever reason """
        del self.upstream_connections[upstream.config.get_ref()]
        print "[%s] UPSTREAM DISCONNECTED FOR %s" % (self.get_name(),upstream.config.get_uri())
        return upstream

    def client_connected(self, client, token):
        """ Called when a client connects for this user."""
        # We need to perform authentication, resource resolution, attach to an upstream,  and possibly replay parts of the cache.
        password,upstreamref,resource = token.split(":")
        if not self.authenticate_client(password):
            raise AuthenticationFailed()
        
        upstreamref = upstreamref.lower()
        client.resource = resource
        client.upstreamref = upstreamref
        client.register_callback(CALLBACK_MESSAGE,self.client_message)
        client.register_callback(CALLBACK_DISCONNECTED,self.client_disconnected)
        self.clients[resource] = client
        if upstreamref in self.upstream_connections:
            client.upstream = self.upstream_connections[upstreamref]
        else:
            upstreamconfig = self.get_upstream_config(upstreamref) 
            if upstreamconfig: # connect on demand
                print "[%s] ON DEMAND CONNECTING TO UPSTREAM %s" % (self.get_name(),upstreamconfig.get_uri())
                d = self.bouncer.connect_upstream(upstreamconfig)
                def __connected(upstream):
                    res = self.upstream_connected(upstream)
                    client.upstream = res
                    return res
                d.addCallback(__connected)
            else:
                raise NoSuchUpstream(upstreamref)

        return client
    def client_message(self, client, line):
        """ Called when a message is received from a client. This message will usually be relayed to the relevant upstream, although it might be diverted to the cache instead. """
        print "[%s][%s][%s] CLIENT_RECV: %s" % (self.get_name(),client.upstreamref,client.resource,line)
        if line.startswith("USER") or line.startswith("NICK"):
            print "[%s][%s][%s] DROPPING_CLIENT_REGISTRATION: %s" % (self.get_name(),client.upstreamref,client.resource,line)
            return
        if client.upstreamref in self.upstream_connections:
            self.upstream_connections[client.upstreamref].sendLine(line)
        else:
            print "[%s][%s][%s] ORPHAN_CLIENT_MSG: %s " % (self.get_name(),client.upstreamref,client.resource,line)
    def client_disconnected(self, client):
        """ Called when a client disconnectes for this user."""
        del self.clients[client.resource]


class IRCBouncer:
    def __init__(self,port,configpath="."):
        self.users = {}
        reactor.listenTCP(port,IRCClientConnectionFactory(self))
        for user_file in glob.glob("%s/*.user" % configpath):
            self.process_user_config(user_file)

    def process_user_config(self, config):
        user = User(self,config)
        print "PROCESSING USER CONFIG FOR %s" % user.get_name()
        self.users[user.get_name()] = user
        for ref, upstreamconfig in user.get_upstream_configs().items():
            print "\t", ref, upstreamconfig.get_uri(), upstreamconfig.get_autoconnect() and "AUTOCONNECT" or "ONDEMAND"
            if upstreamconfig.get_autoconnect():
                d = self.connect_upstream(upstreamconfig)
                def __connected(upstream):
                    return upstream.config.user.upstream_connected(upstream)
                d.addCallback(__connected)

    def connect_upstream(self, upstreamconfig):
        uri = upstreamconfig.get_uri()
        m = re.match("(?:(?P<proto>[a-zA-i0-9]+)://)?(?P<host>[a-zA-Z0-9.-]+)(?:[:](?P<port>[0-9]+))?/?",uri)
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
            return upstream
        d.addCallback(__connected)
        return d

    def connect_client(self, client, token):
        username,sep,token = token.partition(":")
        username = username.lower()
        if username in self.users:
            self.users[username].client_connected(client, token)
        else:
            print "CLIENT CONNECTED WITH UNKNOWN USERNAME: %s" % username



STATE_NONE          = 0
WAITING_FOR_PASS    = 1
CONNECTING_UPSTREAM = 2
FORWARDING          = 3
class IRCClientConnection(CallBackLineReceiver):
    def __init__(self, bouncer):
        CallBackLineReceiver.__init__(self)
        self.bouncer = bouncer
        self.state = STATE_NONE
    def connectionMade(self):
        print "CLIENT CONNECTED"
        self.state = WAITING_FOR_PASS
        self.register_callback(CALLBACK_MESSAGE,self.lineReceived_filter_callback)
    def lineReceived_filter_callback(self,dummy,line):
        if line.startswith("PASS"):
            token = line[5:]
            print "CLIENT CONNECTED WITH TOKEN: %s" % token
            self.bouncer.connect_client(self,token)
            self.unregister_callback(CALLBACK_MESSAGE,self.lineReceived_filter_callback)

class IRCClientConnectionFactory(Factory):
    def __init__(self,bouncer):
        self.bouncer = bouncer
    def buildProtocol(self, addr):
        return IRCClientConnection(self.bouncer)

class IRCUpstreamConnection(CallBackLineReceiver):
    def __init__(self,uri):
        CallBackLineReceiver.__init__(self)
        self.uri = uri
        
class IRCUpstreamConnectionFactory(Factory):
    def __init__(self, uri):
        self.uri = uri
    def buildProtocol(self, addr):
        return IRCUpstreamConnection(self.uri)

if __name__ == '__main__':
    bouncer = IRCBouncer(1234)
    reactor.run()
