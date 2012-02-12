#!/usr/bin/env python2.7
from twisted.internet.protocol import Factory, ClientFactory
from twisted.protocols.basic import LineReceiver
from twisted.internet import reactor
from twisted.internet.endpoints import clientFromString
from passlib.apps import custom_app_context as pwd_context

import re
import yaml
import glob
import uuid

import irc

class UpstreamConfig(object):
    def __init__(self,config,user):
        self.config = config
        self.user = user
    @property
    def uri(self):
        return self.config["uri"]
    @property
    def ref(self):
        return self.config["ref"]
    @property
    def nick(self):
        return self.config.get("nick",self.user.nick)
    @property
    def realname(self):
        return self.config.get("realname",self.user.realname)
    @property
    def autoconnect(self):
        return self.config.get("autoconnect",False)
    @property
    def channel_configs(self):
        if "channels" in self.config:
            return {c["name"].lower(): ChannelConfig(c,self) for c in self.config['channels']}
        return {}
    @property
    def password(self):
        return self.config.get("password","")

class ChannelConfig(object):
    def __init__(self,config,upstreamconfig):
        self.config = config
        self.upstreamconfig = upstreamconfig
    @property
    def name(self):
        return self.config["name"]
    @property
    def key(self):
        return self.config.get("key","")


class ThudException(Exception):
    pass
class AuthenticationFailed(ThudException):
    pass
class NoSuchUpstream(ThudException):
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
    @property
    def name(self):
        return self.config.get('name').lower()
    @property
    def realname(self):
        return self.config.get('realname',self.name)
    @property
    def upstream_configs(self):
        return {c["ref"].lower(): UpstreamConfig(c,self) for c in self.config['upstreams']}
    def get_upstream_config(self, ref):
        return self.upstream_configs.get(ref,None)
    @property
    def nick(self):
        return self.config["nick"]
    @property
    def realname(self):
        return self.config.get("realname",self.name)
    @property
    def password(self):
        return self.config.get("password")

    def authenticate_client(self, password):
        """ Called when a downstream client connects and is attempting to authenticate """
        return pwd_context.verify(password, self.password)

    def upstream_connected(self, upstream):
        """ Called when one of the upstream connections has successfully connected to the upstream server """
        print "[%s] UPSTREAM CONNECTED FOR %s" % (self.name,upstream.config.uri)
        self.upstream_connections[upstream.config.ref] = upstream
        upstream.register_callback(CALLBACK_MESSAGE, self.upstream_message)
        upstream.register_callback(CALLBACK_DISCONNECTED, self.upstream_disconnected)
        upstream.cache = irc.Cache(upstream)
        upstream.register_callback(CALLBACK_MESSAGE,upstream.cache.process_server_message)
        
        # we need to do a USER and NICK command to the server here.
        if upstream.config.password: 
            self.upstream_send(upstream,"PASS %s" % upstream.config.password)
        self.upstream_send(upstream,"NICK %s" % upstream.config.nick)
        self.upstream_send(upstream,"USER %s 0 * :%s" % (upstream.config.nick, upstream.config.realname))
        # we should join all channels:
        for channel in upstream.config.channel_configs.values():
            self.upstream_send(upstream,"JOIN %s %s" % (channel.name, channel.key))
            self.upstream_send(upstream,"MODE %s" % channel.name)
            self.upstream_send(upstream,"WHO %s" % channel.name)

        return upstream
    def upstream_send(self, upstream, line):
        """ Convenience function used to send messages to an upstream server """
        print "[%s][%s] UPSTREAM_SEND: %s" % (self.name,upstream.config.uri,line)
        upstream.sendLine(line)
    def upstream_message(self, upstream, line):
        """ Called when a message is received from an upstream connection. This message will usually be delivered to all clients, and may also be cached."""
        print "[%s][%s] UPSTREAM_RECV: %s" % (self.name,upstream.config.uri,line)
        for resource,client in self.clients.items():
            if client.upstreamref == upstream.config.ref:
                client.sendLine(line)

    def upstream_disconnected(self, upstream):
        """ Called when one of the upstream connections disconnects for whatever reason """
        del self.upstream_connections[upstream.config.ref]
        print "[%s] UPSTREAM DISCONNECTED FOR %s" % (self.name,upstream.config.uri)
        return upstream

    def client_connected(self, client, token):
        """ Called when a client connects for this user."""
        # We need to perform authentication, resource resolution, attach to an upstream,  and possibly replay parts of the cache.
        if token.count(":") == 3:
            password,upstreamref,resource = token.split(":")
        else:
            password,upstreamref = token.split(":")
            resource = uuid.uuid4().hex

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
            client.upstream.cache.attach_client(client)
        else:
            upstreamconfig = self.get_upstream_config(upstreamref) 
            if upstreamconfig: # connect on demand
                print "[%s] ON DEMAND CONNECTING TO UPSTREAM %s" % (self.name,upstreamconfig.uri)
                d = self.bouncer.connect_upstream(upstreamconfig)
                def __connected(upstream):
                    res = self.upstream_connected(upstream)
                    client.upstream = res
                    client.upstream.cache.attach_client(client)
                    return res
                d.addCallback(__connected)
            else:
                raise NoSuchUpstream(upstreamref)
        return client
    def client_message(self, client, line):
        """ Called when a message is received from a client. This message will usually be relayed to the relevant upstream, although it might be diverted to the cache instead. """
        print "[%s][%s][%s] CLIENT_RECV: %s" % (self.name,client.upstreamref,client.resource,line)
        
        if not client.upstreamref in self.upstream_connections:
            print "---> PUTTING OFF FOR 1 SECOND TO GIVE THE UPSTREAM A CHANCE TO COMPLETE CONNECTION!"
            reactor.callLater(1, self.client_message, client, line)
            return
        if client.upstream.cache.handle_client_message(client,line):
            return
        self.upstream_connections[client.upstreamref].sendLine(line)
    def client_disconnected(self, client):
        """ Called when a client disconnectes for this user."""
        print "[%s][%s] CLIENT_DISCONNECTED" % (self.name,client.upstreamref)
        del self.clients[client.resource]



class IRCBouncer:
    def __init__(self,port,configpath="."):
        self.users = {}
        reactor.listenTCP(port,IRCClientConnectionFactory(self))
        for user_file in glob.glob("%s/*.user" % configpath):
            self.process_user_config(user_file)

    def process_user_config(self, config):
        user = User(self,config)
        print "PROCESSING USER CONFIG FOR %s" % user.name
        self.users[user.name] = user
        for ref, upstreamconfig in user.upstream_configs.items():
            print "\t", ref, upstreamconfig.uri, upstreamconfig.autoconnect and "AUTOCONNECT" or "ONDEMAND"
            if upstreamconfig.autoconnect:
                d = self.connect_upstream(upstreamconfig)
                def __connected(upstream):
                    return upstream.config.user.upstream_connected(upstream)
                d.addCallback(__connected)

    def connect_upstream(self, upstreamconfig):
        uri = upstreamconfig.uri
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
        if not ":" in token:
            raise ThudException("Invalid Token!")
        username,sep,token = token.partition(":")
        username = username.lower()
        if username in self.users:
            self.users[username].client_connected(client, token)
        else:
            raise AuthenticationFailed("CLIENT CONNECTED WITH UNKNOWN USERNAME: %s" % username)



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

class IRCClientConnection(CallBackLineReceiver):
    def __init__(self, bouncer):
        CallBackLineReceiver.__init__(self)
        self.bouncer = bouncer
    def connectionMade(self):
        print "CLIENT CONNECTED"
        self.register_callback(CALLBACK_MESSAGE,self.lineReceived_filter_callback)
    def lineReceived_filter_callback(self,dummy,line):
        if line.startswith("PASS"):
            token = line[5:]
            print "CLIENT CONNECTED WITH TOKEN: %s" % token
            try: 
                self.bouncer.connect_client(self,token)
            except AuthenticationFailed:
                print "BAD PASSWORD FOR CLIENT"
                self.sendLine(":THUD 464 :Password is invalid!")
                self.transport.loseConnection()
                return
            except ThudException,e:
                print "SOMETHING WENT AWRY!"
                print e
                self.transport.loseConnection()
                return
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
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4
