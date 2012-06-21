#!/usr/bin/env python2.7
from twisted.internet.protocol import Factory, ReconnectingClientFactory, ClientFactory
from twisted.protocols.basic import LineReceiver
from twisted.internet import reactor, ssl
from twisted.internet.endpoints import clientFromString
from passlib.apps import custom_app_context as pwd_context

import re
import yaml
import glob
import uuid
import time
from datetime import datetime

import irc
import config

class ThudException(Exception):
    pass
class AuthenticationFailed(ThudException):
    pass
class NoSuchNetwork(ThudException):
    pass

class User(object):
    """ This is the central class in thud. A User instance acts as a central point for all clients and server connections. All messages pass through here. """
    def __init__(self, bouncer, config):
        self.bouncer = bouncer
        self.config = config
        self.server_connections = {} #key is ref
        self.server_caches = {} #key is ref
        self.clients = {} # key is resource
        self.logger = [] # no need for keys here
        
    def authenticate_client(self, password):
        """ Called when a downstream client connects and is attempting to authenticate """
        return pwd_context.verify(password, self.config.password)

    def server_connected(self, server):
        """ Called when one of the server connections has successfully connected to the server server """
        print "[%s] SERVER CONNECTED FOR %s" % (self.config.name,server.config.uri)
        self.server_connections[server.config.ref] = server
        server.register_callback(CALLBACK_MESSAGE, self.server_message)
        server.register_callback(CALLBACK_DISCONNECTED, self.server_disconnected)
        if not server.config.ref in self.server_caches:
            self.server_caches[server.config.ref] = irc.Cache(self)
                
        self.server_caches[server.config.ref].set_server(server)
        server.register_callback(CALLBACK_MESSAGE,server.cache.process_server_message)
       
        # we need to do a USER and NICK command to the server here.
        if server.config.get("password"): 
            self.server_send(server,"PASS %s" % server.config.get("password"))
        self.server_send(server,"NICK %s" % server.config.nick)
        self.server_send(server,"USER %s 0 * :%s" % (server.config.nick, server.config.realname))
        # we should join all channels:
        if server.config.channels:
            for channel in server.config.channels:
                self.server_send(server,"JOIN %s %s" % (channel.name, channel.key))
                self.server_send(server,"MODE %s" % channel.name)
                self.server_send(server,"WHO %s" % channel.name)

        return server
    def server_send(self, server, line):
        """ Convenience function used to send messages to an server server """
        print "[%s][%s] SERVER_SEND: %s" % (self.config.name,server.config.uri,line)
        server.sendLine(line)
    def server_message(self, server, line):
        """ Called when a message is received from an server connection. This message will usually be delivered to all clients, and may also be cached."""
        print "[%s][%s] SERVER_RECV: %s" % (self.config.name,server.config.uri,line)
        for resource,client in self.clients.items():
            if client.serverref == server.config.ref:
                client.sendLine(line)

    def server_disconnected(self, server):
        """ Called when one of the server connections disconnects for whatever reason """
        del self.server_connections[server.config.ref]
        print "[%s] SERVER DISCONNECTED FOR %s" % (self.config.name,server.config.uri)
        server.config.reconnect_attempts = 0
        self.server_reconnect(server.config)
        return server
    def server_reconnect(self, networkconfig):
        if networkconfig.reconnect_attempts == 3:
            print "[%s] ABORTING RECONNECT TO %s" % (self.config.name, networkconfig.uri)
            return
        print "[%s] ATTEMPTING RECONNECT TO %s ..." % (self.config.name, networkconfig.uri)
        d = self.bouncer.connect_server(networkconfig,self)
        def __connected(server):
            return server.user.server_connected(server)
        def __error(server):
            networkconfig.reconnect_attempts += 1
            reactor.callLater(pow(2,networkconfig.reconnect_attempts), self.server_reconnect, networkconfig)
        d.addCallbacks(__connected,__error)

    def client_connected(self, client, token):
        """ Called when a client connects for this user."""
        # We need to perform authentication, resource resolution, attach to an server,  and possibly replay parts of the cache.
        if token.count(":") == 2:
            password,serverref,resource = token.split(":")
        else:
            password,serverref = token.split(":")
            resource = uuid.uuid4().hex

        if not self.authenticate_client(password):
            raise AuthenticationFailed()
        
        serverref = serverref.lower()
        client.resource = resource
        client.serverref = serverref
        client.register_callback(CALLBACK_MESSAGE,self.client_message)
        client.register_callback(CALLBACK_DISCONNECTED,self.client_disconnected)
        self.clients[resource] = client
        if not serverref in self.server_connections:
            networkconfig = self.config.by_path("networks/ref=%s" % serverref) 
            if networkconfig: # connect on demand
                print "[%s] ON DEMAND CONNECTING TO SERVER %s" % (self.config.name,networkconfig.uri)
                d = self.bouncer.connect_server(networkconfig,self)
                def __connected(server):
                    res = self.server_connected(server)
                    return res
                d.addCallback(__connected)
            else:
                raise NoSuchNetwork(serverref)
        return client
    def client_message(self, client, line):
        """ Called when a message is received from a client. This message will usually be relayed to the relevant server, although it might be diverted to the cache instead. """
        print "[%s][%s][%s] CLIENT_RECV: %s" % (self.config.name,client.serverref,client.resource,line)
        
        if not client.serverref in self.server_connections:
            print "---> PUTTING OFF FOR 1 SECOND TO GIVE THE SERVER A CHANCE TO COMPLETE CONNECTION!"
            reactor.callLater(1, self.client_message, client, line)
            return
        if self.server_caches[client.serverref].handle_client_message(client,line):
            return
        self.server_connections[client.serverref].sendLine(line)
    def client_disconnected(self, client):
        """ Called when a client disconnectes for this user."""
        print "[%s][%s] CLIENT_DISCONNECTED" % (self.config.name,client.serverref)
        del self.clients[client.resource]

class IRCBouncer:
    def __init__(self,port,configpath="."):
        self.users = {}
        self.process_server_config("%s/thud.conf" % configpath)
        factory = IRCClientConnectionFactory(self)

        if self.config.ssl_enable:        
            print "LISTENING ON PORT %d for SSL" % self.config.ssl_port
            try:
                reactor.listenSSL(self.config.ssl_port, factory, ssl.DefaultOpenSSLContextFactory(self.config.ssl_key, self.config.ssl_cert))
            except Exception,e:
                print "FAILED TO LISTEN FOR SSL: %s" % e
        
        if self.config.tcp_enable:
            print "LISTENING ON PORT %d for TCP" % self.config.tcp_port
            reactor.listenTCP(self.config.tcp_port, factory)
        
        for user_file in glob.glob("%s/*.user" % configpath):
            self.process_user_config(user_file)

    def process_server_config(self, filename):
        print "PROCESSING SERVER CONFIG"
        self.config = config.Config(filename=filename)
        
    def process_user_config(self, filename):
        userconfig = config.Config(filename=filename,parent=self.config)
        user = User(self,userconfig)
        print "PROCESSING USER CONFIG FOR %s" % user.config.name
        self.users[user.config.name] = user
        for networkconfig in user.config.networks:
            print "\t", networkconfig.ref, networkconfig.uri, networkconfig.autoconnect and "AUTOCONNECT" or "ONDEMAND"
            if networkconfig.autoconnect:
                d = self.connect_server(networkconfig,user)
                def __connected(server):
                    return server.user.server_connected(server)
                d.addCallback(__connected)

    def connect_server(self, networkconfig, user):
        uri = networkconfig.uri
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
        d = endpoint.connect(IRCServerConnectionFactory(uri))
        def __connected(server):
            print "SERVER_CONNECTED!"
            server.config = networkconfig
            server.user = user
            return server
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

class IRCLogger(object):
    def __init__(self):
        self.file_template = None
        self.file_opened = 0
        self.file = None
        self.enable = False
        self.name = None
        self.server = None
        self.timestamp_template = None
        self.last_activity = time.time()

    def read_config(self, config):
        pass

    def open_file_required(self, now):
        if self.file == None:
            return True
            
        if (now - self.file_opened) > (60*60*24):
            return True
            
        new = datetime.fromtimestamp(now)
        old = datetime.fromtimestamp(self.file_opened)
        if old.day != new.dat:
            return True

        return False
        
    def open_file(self, now):
        if self.open_file_required(now) != True:
            return
       
        # XXX: fail, too lazy to figure out a sane way to do this...
        dt = datetime.fromtimestamp(now)
        fname = self.file_template
        fname = fname.replace('%y', dt.year)
        fname = fname.replace('%m', dt.month)
        fname = fname.replace('%d', dt.day)
        fname = fname.replace('%n', self.server)
        fname = fname.replace('%c', self.name)

        self.file = open(fname, 'a+')
        self.file_opened = now

    def shutdown(self):
        self.file.close()
        self.file_opened = 0

    def format_timestamp(self, timestamp):
        timestamp = datetime.fromtimestamp(timestamp)
        return '%02d:%02d:%02d' % (timestamp.hour, timestamp.minute, timestamp.second)
        
    def log(self, timestamp, message):
        message = '[%s] %s' % (self.format_timestamp(timestamp), message)
        print '-------- %s' % message
        return
        self.open_file(timestamp)
        self.file.write(message + '\n')
        self.last_activity = time.time()
        
    def clone(self):
        clone = IRCLogger()
        clone.file_template = self.file_template
        clone.enable = self.enable
        clone.timestamp_template = self.timestamp_template
        clone.server = self.server
        return clone

    def log_join(self, now, name):
        self.log(now, '*** %s has joined' % name)

    def log_topic(self, now, name, topic):
        self.log(now, '*** topic has been set by %s to: %s' % (name, topic))      

    def log_mode(self, user, message):
        self.log(time.time(), "*** %s sets mode %s" % (user, ' '.join(message)))
        pass

    def log_privmsg(self, now, source, message):
        self.log(now, '<%s> %s' % (source, message))


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
    def sendLine(self,line):
        #print "CLIENT SENDLINE: %s" % line
        if len(line.strip()):
            CallBackLineReceiver.sendLine(self,line)
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

class IRCServerConnection(CallBackLineReceiver):
    def __init__(self,uri):
        CallBackLineReceiver.__init__(self)
        self.uri = uri
        
class IRCServerConnectionFactory(Factory):
    def __init__(self, uri):
        self.uri = uri
    def buildProtocol(self, addr):
        return IRCServerConnection(self.uri)

if __name__ == '__main__':
    bouncer = IRCBouncer(1234)
    reactor.run()
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4
