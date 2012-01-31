#!/usr/bin/env python2.7
from twisted.internet.protocol import Factory, ClientFactory
from twisted.protocols.basic import LineReceiver
from twisted.internet import reactor
from twisted.internet.endpoints import clientFromString
import uuid
import re


STATE_NONE          = 0
WAITING_FOR_PASS    = 1
CONNECTING_UPSTREAM = 2
FORWARDING          = 3
class IRCProxy(LineReceiver):
    state = STATE_NONE
    def connectionMade(self):
        print "CLIENT CONNECTED"
        self.state = WAITING_FOR_PASS
    def lineReceived(self,line):
        if self.state == FORWARDING:
            print "FORWARDING FROM CLIENT: %s" % line
            self.upstream.sendLine(line)
            return 
        print "RECEIVED FROM CLIENT: %s" % line
        if self.state == WAITING_FOR_PASS and line.startswith("PASS"):
            uri = line[5:]
            print "REQUESTING UPSTREAM: %s" % uri
            self.state = CONNECTING_UPSTREAM
            self.factory.attach_upstream(uri,self)
    def upstream_attached(self, upstream):
        self.upstream = upstream
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
        if qs:
            for kv in qs.split("&"):
                key,value = kv.split("=")
                args[key] = value
        return uri, args
    def attach_upstream(self, uri, client):
        print "REQUESTED attach to upstream %s" % uri
        uri, args = self.parse_uri(uri)

        def __upstream_connected(upstream):
            print "UPSTREAM_CONNECTED!"
            self.upstream_connections[uri] = upstream
            upstream.register_client(client,args)
            client.upstream_attached(upstream)
        if uri in self.upstream_connections:
            __upstream_connected(self.upstream_connections[uri])
        else:
            d = self.connect_upstream(uri,client,args)
            d.addCallback(__upstream_connected)

    def connect_upstream(self, uri, client, args):
        m = re.match("(?:(?P<proto>[a-zA-i0-9]+)://)?(?P<host>[a-zA-Z0-9.-]+)(:?P<port>[0-9]+)?/?",uri)
        parts = m.groupdict()
        protocol = parts.get("proto","ircs").lower()
        host = parts.get("host")
        port = parts.get("port","6667")

        if protocol == "irc":
            epproto = "tcp"
        elif protocol == "ircs":
            epproto = "ssl"
        endpointstring = "%s:host=%s:port=%s" % (epproto,host,port)
        endpoint = clientFromString(reactor,endpointstring)
        return endpoint.connect(IRCUpstreamConnectionFactory(uri))



class IRCUpstreamConnection(LineReceiver):
    def __init__(self,uri):
        self.uri = uri
        self.clients = {}
    def register_client(self, client, args):
        if "resource" in args:
            resource = args[resource]
        else:
            # use a random resource identifier
            resource = uuid.uuid4().hex
        self.clients[resource] = client
        client.resource = resource

    def unregister_client(self, client):
        if client.resource in self.clients:
            del self.clients[client.resource]

    def lineReceived(self,line):
        print "FORWARDING TO CLIENTS: %s" % line
        for client in self.clients.values():
            client.sendLine(line)
        
class IRCUpstreamConnectionFactory(Factory):
    def __init__(self, uri):
        self.uri = uri
    def buildProtocol(self, addr):
        return IRCUpstreamConnection(self.uri)

reactor.listenTCP(1234,IRCProxyFactory())
#reactor.connectTCP("localhost",1234,IRCUpstreamConnectionFactory())
reactor.run()
