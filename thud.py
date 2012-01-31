#!/usr/bin/env python
from twisted.internet.protocol import Factory, ClientFactory
from twisted.protocols.basic import LineReceiver
from twisted.internet import reactor
from twisted.internet.endpoints import clientFromString


STATE_NONE          = 0
WAITING_FOR_PASS    = 1
CONNECTING_UPSTREAM = 2
FORWARDING          = 3
class IRCProxy(LineReceiver):
    state = STATE_NONE
    def connectionMade(self):
        print "CONNECTED!!!"
        self.state = WAITING_FOR_PASS
    def lineReceived(self,line):
        if self.state == FORWARDING:
            print "FORWARDING: %s" % line
            self.sendLine(self.upstream.sendreceive(line))
            return 
        print "RECEIVED: %s" % line
        if self.state == WAITING_FOR_PASS and line.startswith("PASS"):
            upstream = line[5:]
            print "REQUESTING UPSTREAM: %s" % upstream
            self.state = CONNECTING_UPSTREAM
            if upstream in self.factory.upstream_connections:
                self.upstream = self.factory.upstream_connections[upstream]
            else:
                self.upstream = self.factory.connect_upstream(upstream)
            self.state = FORWARDING
            

class IRCProxyFactory(Factory):
    protocol = IRCProxy
    def __init__(self):
        self.upstream_connections = {}
    def parse_uri(self, uri):
        qs = ""
        if "?" in uri:
            uri, qs = uri.split("?")
        args = {}
        for kv in qs.split("&"):
            key,value = kv.split("=")
            args[key] = value
        return uri, args
    def attach_upstream(self, uri, client):
        print "REQUESTED attach to upstream %s" % uri
        uri, args = self.parse_uri(uri)
        if uri in self.upstream_connections:
            upstream = self.upstream_connections[uri]
        else:
            upstream = self.connect_upstream(uri,args)
            self.upstream_connections[uri] = upstream

    def connect_upstream(self, uri, client, args):
        m = re.match("((?P<proto>[a-zA-i0-9]+)://)?(?P<host>[a-zA-Z0-9.-]+)(:?P<port>[0-9]+)?/?",uri)
        protocol = m.group("proto").lower()
        if protocol == "irc":
            epproto = "tcp"
        elif protocol == "ircs":
            epproto = "ssl"
        endpointstring = "%s:host=%s:port=%s" % (epproto,m.group("host"),m.group("port"))
        endpoint = clientFromString(reactor,endpointstring)
        d = endpoint.connect(IRCUpstreamConnectionFactory(uri))
        def __upstream_connected(p):
            p.register_client(client,args)
        d.addCallback(__upstream_connected)



class IRCUpstreamConnection(LineReceiver):
    def __init__(self,uri):
        self.uri = uri
        self.clients = {}
    def register_client(self, client, args):
        if "resource" in args:
            resource = args[resource]
        else:
            resource = random()
        self.clients[resource] = client

    def sendreceive(self, line):
        print "%s wants to FORWARD: %s" % (self.uri,line)
        return ""

class IRCUpstreamConnectionFactory(Factory):
    def __init__(self, uri):
        self.uri = uri
    def buildProtocol(self, addr):
        return IRCUpstreamConnection(self.uri)

reactor.listenTCP(1234,IRCProxyFactory())
reactor.connectTCP("localhost",1234,IRCUpstreamConnectionFactory())
reactor.run()
