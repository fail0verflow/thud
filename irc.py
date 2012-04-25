from collections import deque, OrderedDict, defaultdict
from datetime import datetime
import time
class MessageBuffer(object):
    def __init__(self,config, maxlen=0):
        self.config = config
        if not maxlen:
            maxlen = self.config.backlog_depth
        self.messages = deque(maxlen=maxlen)

    def log_message(self, timestamp, message):
        pass
    def add_message(self, message):
        timestamp = datetime.now()
        self.log_message(timestamp,message)
        self.messages.append((timestamp,message))
        #TODO: logging

    def get_messages_since(self, last_time):
        print "REPLAYING MESSAGES SINCE %s" % last_time
        messages = []
        for stamp, message in self.messages:
            print "DBG: stamp: %s, msg: %s" % (stamp, message)
            if stamp > last_time:
                messages.append(message)
        return messages

    def rejoin(self, client, last_seen):
        # replay messages since the last_seen time.
        client.sendLine("\n".join(self.get_messages_since(last_seen)))

class ChannelBuffer(MessageBuffer):
    def __init__(self,name, config):
        MessageBuffer.__init__(self,config)
        self.init = []
        self.name = name
        self.topic = ""
        self.who = []
        self.mode = []

    def rejoin(self, client, last_seen):
        client.sendLine("\n".join(self.init))
        client.sendLine(self.topic)
        messages = self.get_messages_since(last_seen)
        client.sendLine(":thud!cache@th.ud NOTICE %s :Welcome back! You were last here at %s. Since then, there have been %d messages, replayed below:" % (self.name, last_seen, len(messages)))
        client.sendLine("\n".join(messages))
class QueryBuffer(MessageBuffer):
    def __init__(self,nick, config):
        MessageBuffer.__init__(self,config,config.query_backlog_depth)
        self.nick = nick


class DummyLogger(object):
    def call(self, *args):
        pass
    
class Cache(object):
    def __init__(self):
        self.upstream = None
        self.welcome = []
        self.motd = []
        self.mode = []
        self.channels = {}
        self.queries = {}
        self.nick = None
        # dictionary keyed on client resource, which lists when each resource was last known to be alive.
        self.last_seen = defaultdict(lambda: datetime.fromordinal(1))
        self.logger = {} # 'configured' loggers; key is channel name
        self.temp_logger = {} # 'temporary' loggers, created for unconfigured channels and privmsg; deleted after inactivity; key is channel/user name
        self.default_logger = None # logger base class for newly joined channels and privmsgs

    def add_logger(self, channel, logger):
        if channel == None:
            self.default_logger = logger
        else:
            self.logger[channel] = logger

    def get_logger(self, name):
        if name in self.logger.items():
            if self.logger[name] == None:
                return DummyLogger()
            return self.logger[name]

        # this is never None: all temp_loggers are based on default_logger and only created when default_logger != None
        if name in self.temp_logger.items():
            return self.temp_logger[name]

        if self.default_logger == None:
            return DummyLogger()

        self.temp_logger[name] = self.default_logger.clone()
        self.temp_logger[name].name = name
        return self.temp_logger[name]

    def parse_message(self, message):
        prefix = ""
        if message.startswith(":"):
            prefix,code,args = message.split(" ",2)
        else:
            code,args = message.split(" ",1)
        if ":" in args:
            args,d,last_arg = args.partition(":")
            args = args.split() + [last_arg]
        else:
            args = args.split(" ")
        if code.isdigit():
            code = int(code)
            if code in numeric_codes_reverse:
                code = numeric_codes_reverse[int(code)]
        #print "CACHE -------- FROM %s TYPE %s ARGS %s" % (prefix, code,args)
        return (prefix,code,args)

    def dispatch_server_message(self, source, message):
        prefix, code, args = self.parse_message(message)
        handler = getattr(self,'handle_server_%s' % code, None)
        if handler:
            return handler(source, message, prefix, code, args)
        print "CACHE UNABLE TO DISPATCH UNKNOWN MESSAGE CODE: %s" % message
        return None

    def process_server_message(self,upstream,message):
        """ Called with each message from the upstream server. The message should be parsed, analyzed and possibly added to the cache's data-stores."""
        print "CACHE RECEIVED: %s" % message
        self.dispatch_server_message(upstream,message)

    def update_last_seen(self,client):
        print "[*] UPDATE LAST_SEEN FOR %s" % client.resource
        self.last_seen[client.resource] = datetime.now()

    def handle_client_message(self,client, message):
        """ Called with each message from the client. The message should be parsed and if the cache can handle the message it should send any responses necessary and return true. If the cache can't handle the message, return false."""
        prefix, code, args = self.parse_message(message)
        last_seen = self.last_seen[client.resource]
        if code == "USER":
            print "REGISTERING CLIENT: %s" % (message)
            print "RESOURCE (%s) LAST SEEN AT %s" % (client.resource, last_seen)
            client.sendLine("\n".join(self.welcome))
            client.sendLine("\n".join(self.motd))
            client.sendLine("\n".join(self.mode))
            client.sendLine("\n".join(self.queries))
            #TODO: send privmsgs and register resource
            for channel in self.channels.values():
                print "FORCING CLIENT JOIN TO CHANNEL %s" % channel.name
                channel.rejoin(client,last_seen)
            for query in self.queries.values():
                print "FORCING CLIENT JOIN TO QUERY %s" % query.nick
                query.rejoin(client,last_seen)
        elif code in ["QUIT"]:
            # just update last_seen
            pass
        elif code == "PRIVMSG":
            timestamp = time.time()
            now = datetime.fromtimestamp(timestamp)
            if args[0] in self.channels:
                self.channels[args[0]].add_message(message)
            else:
                nick = args[0]
                if not nick in self.queries:
                    self.queries[nick] = QueryBuffer(nick,self.upstream.config)
                print "QUERY SEND [%s] %s" % (nick,message)
                self.queries[nick].add_message(message)
            # update last_seen, but return false so that the message is sent to the server 
            self.update_last_seen(client)
            return False
        elif code == "JOIN" and args[0] in self.channels:
            print "GOT JOIN MESSAGE FOR %s" % args[0]
            self.channels[args[0]].rejoin(client,last_seen)
        elif code == "MODE" and args[0] in self.channels and len(self.channels[args[0]].mode):
            client.sendLine("\n".join(self.channels[args[0]].mode))
        elif code == "WHO" and args[0] in self.channels and len(self.channels[args[0]].who):
            client.sendLine("\n".join(self.channels[args[0]].who))
        else:
            print "CACHE IGNORING CLIENT MESSAGE %s:%s" % (code,args)
            return False
        self.update_last_seen(client)
        return True

    def attach_client(self, client):
        """ Called when a client wishes to attach to the cache. Should send the welcome, motd and privmsg/query caches to him, as well as registering his resource for channel backlogs. """
        #Not sure we should be pushing all these channels out, but hey why not:
        for channel in self.channels.values():
            print "PUSHING CHANNEL: %s" % channel.name
            client.sendLine("\n".join(channel.init))
            client.sendLine("\n".join(channel.mode))
            client.sendLine("\n".join(channel.who))
            client.sendLine("\n".join(channel.topic))
            print "BACKLOGGING: \n\t%s" % "\n\t".join(OrderedDict(channel.messages).values())
            client.sendLine("\n".join(OrderedDict(channel.messages).values()))

    # WELCOME
    def handle_server_RPL_WELCOME(self, source, message, prefix, code, args):
        self.welcome = []
        self.welcome.append(message)
    def handle_server_welcome_messages(self, source, message, prefix, code, args):
        self.welcome.append(message)
    handle_server_RPL_YOURHOST=handle_server_welcome_messages
    handle_server_RPL_CREATED =handle_server_welcome_messages
    handle_server_RPL_MYINFO  =handle_server_welcome_messages
    handle_server_RPL_ISUPPORT=handle_server_welcome_messages

    # MOTD
    def handle_server_RPL_MOTDSTART(self, source, message, prefix, code, args):
        self.motd = []
        self.motd.append(message)
    def handle_server_RPL_MOTD(self, source, message, prefix, code, args):
        self.motd.append(message)
    def handle_server_RPL_ENDOFMOTD(self, source, message, prefix, code, args):
        self.motd.append(message)

    def handle_server_MODE(self, source, message, prefix, code, args):
        self.mode = message
        self.get_logger(args[1]).log_mode(prefix, args)

    # CHANNEL JOIN
    def handle_server_JOIN(self, source, message, prefix, code, args):
        name = args[0]
        self.channels[name] = ChannelBuffer(name,self.upstream.config.channel_configs.get(name,None))
        self.channels[name].init.append(message)
        self.get_logger(name).log_join(time.time(), prefix)
    def handle_server_RPL_NAMREPLY(self, source, message, prefix, code, args):
        name = args[1] in ["=","*","@"] and args[2] or args[1]
        self.channels[name].init.append(message)
    def handle_server_RPL_ENDOFNAMES(self, source, message, prefix, code, args):
        self.channels[args[1]].init.append(message)

    def handle_server_TOPIC(self, source, message, prefix, code, args):
        self.channels[args[0]].topic = message
        self.get_logger(args[0]).log_topic(time.time(), prefix, args[1])

    # CHANNEL MODE
    def handle_server_RPL_CHANNELMODEIS(self, source, message, prefix, code, args):
        print "CACHEING CHANNEL MODE: %s" % message
        self.channels[args[1]].mode = [message]
    def handle_server_RPL_CREATIONTIME(self, source, message, prefix, code, args):
        self.channels[args[1]].mode.append(message)

    # CHANNEL WHO
    def handle_server_RPL_WHOREPLY(self, source, message, prefix, code, args):
        self.channels[args[1]].who.append(message)
    handle_server_RPL_ENDOFWHO = handle_server_RPL_WHOREPLY

    # PING
    def handle_server_PING(self, source, message, prefix, code, args):
        source.sendLine("PONG %s" % args[0])

    # NICK
    def handle_server_NICK(self, source, message, prefix, code, args):
        self.nick = args[0]

    # PRIVMSG
    def handle_server_PRIVMSG(self, source, message, prefix, code, args):
        timestamp = time.time()
        now = datetime.fromtimestamp(timestamp)
        if args[0] in self.channels:
            self.channels[args[0]].add_message(message)
        else:
            nick = prefix[1:].partition("!")[0]
            if not nick in self.queries:
                self.queries[nick] = QueryBuffer(nick,self.upstream.config)
            print "QUERY RCV [%s] %s" % (nick,message)
            self.queries[nick].add_message(message)
        #self.get_logger(args[0]).log_privmsg(timestamp, prefix, args[1])



# Numeric response codes
# Source: http://libircclient.sourceforge.net/group__rfcnumbers.html
# and: https://www.alien.net.au/irc/irc2numerics.html

numeric_codes = {
    'RPL_WELCOME'     : 001,
    'RPL_YOURHOST'    : 002,
    'RPL_CREATED'     : 003,
    'RPL_MYINFO'      : 004,
    'RPL_ISUPPORT'    : 005,

    'RPL_USERHOST'    : 302,
    'RPL_ISON'        : 303,
    'RPL_AWAY'        : 301,
    'RPL_UNAWAY'      : 305,
    'RPL_NOWAWAY'     : 306,

    'RPL_WHOISUSER'   : 311,
    'RPL_WHOISSERVER' : 312,
    'RPL_WHOISOPERATOR'    : 313,
    'RPL_WHOISIDLE'   : 317,
    'RPL_ENDOFWHOIS'  : 318,
    'RPL_WHOISCHANNELS' : 319,
    'RPL_WHOWASUSER'  : 314,
    'RPL_ENDOFWHOWAS' : 369,
    'RPL_LIST'        : 322,
    'RPL_LISTEND'     : 323,
    'RPL_UNIQOPIS'    : 325,
    'RPL_CHANNELMODEIS' : 324,
    'RPL_CREATIONTIME' : 329,
    'RPL_NOTOPIC'     : 331,
    'RPL_TOPIC'       : 332,
    'RPL_INVITING'    : 341,
    'RPL_SUMMONING'   : 342,
    'RPL_INVITELIST'  : 346,
    'RPL_ENDOFINVITELIST' : 347,
    'RPL_EXCEPTLIST'  : 348,
    'RPL_ENDOFEXCEPTLIST' : 349,
    'RPL_VERSION'     : 351,
    'RPL_WHOREPLY'    : 352,
    'RPL_ENDOFWHO'    : 315,
    'RPL_NAMREPLY'   : 353,
    'RPL_ENDOFNAMES'  : 366,
    'RPL_LINKS'       : 364,
    'RPL_ENDOFLINKS'  : 365,
    'RPL_BANLIST'     : 367,
    'RPL_ENDOFBANLIST'    : 368,
    'RPL_INFO'        : 371,
    'RPL_ENDOFINFO'   : 374,
    'RPL_MOTDSTART'   : 375,
    'RPL_MOTD'        : 372,
    'RPL_ENDOFMOTD'   : 376,
    'RPL_YOUREOPER'   : 381,
    'RPL_REHASHING'   : 382,
    'RPL_YOURSERVICE' : 383,
    'RPL_TIME'        : 391,
    'RPL_USERSTART'   : 392,
    'RPL_USERS'       : 393,
    'RPL_ENDOFUSERS'  : 394,
    'RPL_NOUSERS'     : 395,
    'RPL_TRACELINK'   : 200,
    'RPL_TRACECONNECTING' : 201,
    'RPL_TRACEHANDSHAKE' : 202,
    'RPL_TRACEUNKNOWN' : 203,
    'RPL_TRACEOPERATOR' : 204,
    'RPL_TRACEUSER'   : 205,
    'RPL_TRACESERVER' : 206,
    'RPL_TRACESERVICE' : 207,
    'RPL_TRACENEWTYPE' : 208,
    'RPL_TRACECLASS'  : 209,
    'RPL_TRACELOG'    : 261,
    'RPL_TRACEEND'    : 262,
    'RPL_STATSLINKINFO' : 211,
    'RPL_STATSCOMMANDS' : 212,
    'RPL_ENDOFSTATS'  : 219,
    'RPL_STATSUPTIME' : 242,
    'RPL_STATSOLINE'  : 243,
    'RPL_UMODEIS'     : 221,
    'RPL_SERGVLIST'   : 234,
    'RPL_SERVLISTEND' : 235,
    'RPL_STATSDLINE' : 250,
    'RPL_LUSERCLIENT' : 251,
    'RPL_LUSEROP'     : 252,
    'RPL_LUSERUNKNOWN' : 253,
    'RPL_LUSERCHANNELS' : 254,
    'RPL_LUSERME'     : 255,
    'RPL_LADMINME'    : 256,
    'RPL_ADMINLOC1'   : 257,
    'RPL_ADMINLOC2'   : 258,
    'RPL_ADMINEMAIL'  : 259,
    'RPL_TRYAGAIN'    : 263,
    'RPL_LOCALUSERS'     : 265,
    'RPL_GLOBALUSERS'     : 266,
    'ERR_NOSUCHNICK'      : 401,
    'ERR_NOSUCHSERVER'    : 402,
    'ERR_NOSUCHCHANNEL'   : 403,
    'ERR_CANNOTSENDTOCHAN': 404,
    'ERR_TOOMANYCHANNELS' : 405,
    'ERR_WASNOSUCHNICK'   : 406,
    'ERR_TOOMANYTARGETS'  : 407,
    'ERR_NOSUCHSERVICE'   : 408,
    'ERR_NOORIGIN'        : 409,
    'ERR_NORECIPIENT'     : 411,
    'ERR_NOTEXTTOSEND'    : 412,
    'ERR_NOTOPLEVEL'      : 413,
    'ERR_WILDTOPLEVEL'    : 414,
    'ERR_BADMASK'         : 415,
    'ERR_UNKNOWNCOMMAND'  : 421,
    'ERR_NOMOTD'          : 422,
    'ERR_NOADMININFO'     : 423,
    'ERR_FILEERROR'       : 424,
    'ERR_NONICKNAMEGIVEN' : 431,
    'ERR_ERRONEUSNICKNAME': 432,
    'ERR_NICKNAMEINUSE'   : 433,
    'ERR_NICKCOLLISION'   : 436,
    'ERR_UNAVAILRESOURCE' : 437,
    'ERR_USERNOTINCHANNEL': 441,
    'ERR_NOTONCHANNEL'    : 442,
    'ERR_USERONCHANNEL'   : 443,
    'ERR_NOLOGIN'         : 444,
    'ERR_SUMMONDISABLED'  : 445,
    'ERR_USERSDISABLED'   : 446,
    'ERR_NOTREGISTERED'   : 451,
    'ERR_NEEDMOREPARAMS'  : 461,
    'ERR_ALREADYREGISTERED':462,
    'ERR_NOPERMFORHOST'   : 463,
    'ERR_PASSWDMISMATCH'  : 464,
    'ERR_YOUREBANNEDCREEP': 465,
    'ERR_YOUWILLBEBANNED' : 466,
    'ERR_KEYSET'          : 467,
    'ERR_CHANNELISFULL'   : 471,
    'ERR_UNKNOWNMODE'     : 472,
    'ERR_INVITEONLYCHAN'  : 473,
    'ERR_BANNEDFROMCHAN'  : 474,
    'ERR_BADCHANNELKEY'    : 475,
    'ERR_BADCHANMASK'     : 476,
    'ERR_NOCHANMODES'     : 477,
    'ERR_BANLISTFULL'     : 478,
    'ERR_NOPRIVELEGES'    : 481,
    'ERR_CHANOPRIVSNEEDED': 482,
    'ERR_CANTKILLSERVER'  : 483,
    'ERR_RESTRICTED'      : 484,
    'ERR_UNIQOPPRIVSNEEDED':485,
    'ERR_NOOPERHOST'      : 491,
    'ERR_UMODEUNKNOWNFLAG': 501,
    'ERR_USERSDONTMATCH'  : 502,
}
numeric_codes_reverse = {v: k for k,v in numeric_codes.items() }
# merge into module:
globals().update(numeric_codes)

# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4
