from collections import deque, defaultdict
from datetime import datetime
import thudshell


def parse_message(message):
    prefix = ""
    if message.startswith(":"):
        prefix, code, args = message.split(" ", 2)
    else:
        if " " in message:
            code, args = message.split(" ", 1)
        else:
            code, args = (message, "")

    if ":" in args:
        if args[0] == ":":
            args = " " + args
        args, d, last_arg = args.partition(" :")
        args = args.split() + [last_arg]
    else:
        args = args.split(" ")
    if code.isdigit():
        code = int(code)
        if code in numeric_codes_reverse:
            code = numeric_codes_reverse[int(code)]
    return (prefix, code, args)


def nick_from_prefix(prefix):
    return prefix[1:].partition("!")[0]


def host_from_prefix(prefix):
    return prefix.partition("@")[2]


def make_prefix(nick, host):
    return ":%s!%s@%s" % (nick, nick, host)


class MessageLogger(object):
    def __init__(self, config, server, name):
        self.config, self.server, self.name = config, server, name
        self.file_template = config.log_file_template
        self.timestamp_template = config.log_timestamp_template
        self.open_file()

    def open_file(self):
        if self.file:
            self.file.close()
        self.file_opened = datetime.now()
        filename = self.file_opened.strftime(self.file_template.replace("%SERVER", self.server).replace("%CHANNEL", self.name))
        self.file = open(filename, 'at')

    def log(self, timestamp, message):
        if timestamp.day > self.file_opened.day:
            self.open_file()
        prefix, code, args = message
        if code == "PRIVMSG":
            self.file.writeline("%s: <%s> %s" % (timestamp.strftime(self.timestamp_template), prefix[1:].partition("!")[0], args))


class MessageBuffer(object):
    def __init__(self, config, maxlen=0):
        self.config = config
        if not maxlen:
            maxlen = self.config.backlog_depth
        self.messages = deque(maxlen=maxlen)
        if 0 and self.config.logging:
            self.logger = MessageLogger(self.config)
            self.log_message = self._log_message
        else:
            self.log_message = lambda x, y: None

    def _log_message(self, timestamp, message):
        self.logger.log(timestamp, message)

    def add_message(self, message):
        timestamp = datetime.now()
        self.log_message(timestamp, message)
        self.messages.append((timestamp, message))

    def get_messages_since(self, last_time):
        print "REPLAYING MESSAGES SINCE %s" % last_time
        messages = []
        for stamp, message in self.messages:
            if stamp > last_time:
                #TODO: make this configurable!
                prefix, code, args = parse_message(message)
                if not prefix:
                    prefix = make_prefix(self.cache.nick, self.cache.host)
                message = "%s %s %s :[%s] %s" % (prefix, code, args[0], stamp.strftime("%H:%M:%S"), args[1])
                messages.append(message)
        return messages

    def rejoin(self, client, last_seen):
        # replay messages since the last_seen time.
        client.sendLine("\n".join(self.get_messages_since(last_seen)))


class ChannelMember(object):
    def __init__(self, whoargs):
        self.user, self.host, self.server, self.nick, modestring = whoargs[:5]
        self.hops, dummy, self.realname = whoargs[5].partition(" ")
        self.away = modestring[0] == "G"
        self.ircoper = len(modestring) > 1 and modestring[1] == "*"
        self.mode = self.ircoper and modestring[2:] or modestring[1:]

    def get_modestring(self):
        modestring = self.away and "G" or "H"
        modestring += self.ircoper and "*" or ""
        modestring += self.mode
        return modestring

    def __repr__(self):
        return "%s %s %s %s %s :%s %s" % (self.user, self.host, self.server, self.nick, self.get_modestring(), self.hops, self.realname)

    def update_modes(self, mode):
        if mode == "+o":
            self.mode = "@"
        elif mode == "-o" and self.mode == "@":
            self.mode = ""
        elif mode == "+v" and not self.mode:
            self.mode = "+"
        elif mode == "-v" and self.mode == "+":
            self.mode = ""


class ChannelBuffer(MessageBuffer):
    def __init__(self, name, cache, config):
        MessageBuffer.__init__(self, config)
        self.cache = cache
        self.name = name
        self.init_vars()
        self.has_who = False

    def init_vars(self):
        self.members = {}
        self.topic = ""
        self.join = ""
        self.who = []
        self.mode = []
        self.is_joined = True

    def rejoin(self, client, last_seen):
        client.sendLine("%s JOIN %s" % (make_prefix(self.cache.nick, self.cache.host), self.name))
        #TODO: FETCH the topic if we don't have one
        client.sendLine("%s 332 %s %s :%s" % (self.cache.serverprefix, self.cache.nick, self.name, self.topic))
        client.sendLine("\n".join(self.mode))
        client.sendLine("\n".join(self.get_names()))
        messages = self.get_messages_since(last_seen)
        client.sendLine(":thud!cache@th.ud NOTICE %s :Welcome back! You were last here at %s. Since then, there have been %d messages, replayed below:" % (self.name, last_seen, len(messages)))
        client.sendLine("\n".join(messages))

    def part(self):
        print "[-] PART %s" % self.name
        self.is_joined = False

    def add_join(self, message, prefix, code, args):
        print "[-] ADD_JOIN(%s)" % message
        if nick_from_prefix(prefix) == self.cache.nick:
            print "[-] ACTUALLY JOINING %s" % self.name
            self.init_vars()
        else:
            self.members[nick_from_prefix(prefix)] = None  # just add the nick to the dictionary
            # TODO: send a WHO to the server for this user on this channel so that we can build a ChannelMember

    def add_part(self, message, prefix, code, args):
        print "[-] ADD_PART(%s)" % message
        if nick_from_prefix(prefix) == self.cache.nick:
            self.is_joined = False
        else:
            del self.members[nick_from_prefix(prefix)]

    def add_names(self, message, prefix, code, args):
        #print "[-] ADD_NAMES(%s)" % message
        if code == "RPL_NAMREPLY":
            for name in args[3].split(" "):
                if name.startswith("@") or name.startswith("+"):
                    name = name[1:]
                if not name in self.members:
                    self.members[name] = None

    def get_names(self):
        messages = []
        names = self.members.keys()
        while names:
            messages.append("%s 353 %s = %s :%s" % (self.cache.serverprefix, self.cache.nick, self.name, " ".join(names[:3])))
            names = names[3:]
        messages.append("%s 366 %s %s :End of NAMES list" % (self.cache.serverprefix, self.cache.nick, self.name))
        return messages

    def update_nick(self, old, new):
        if old in self.members:
            tmp = self.members[old]
            tmp.nick = new
            self.members[new] = tmp
            del self.members[old]

    def set_topic(self, message, prefix, code, args):
        print "[-] SET_TOPIC(%s)" % message
        self.topic = args[2]

    def add_channel_mode(self, message, prefix, code, args):
        print "[-] ADD_CHANNEL_MODE(%s)" % message
        self.mode.append(message)

    def add_mode(self, message, prefix, code, args):
        print "[-] ADD_MODE(%s)" % message
        print args
        if len(args) < 3:
            self.add_channel_mode(message, prefix, code, args)
            return
        if not args[2] in self.members:
            print "\n" * 5 + "channel member not found: " + args + "\n" * 5
            return
        self.members[args[2]].update_modes(args[1])

    def add_who(self, message, prefix, code, args):
        #print "[-] ADD_WHO(%s)" % message
        if code == "RPL_WHOREPLY":
            self.members[args[5]] = ChannelMember(args[2:])
        self.has_who = True

    def get_who(self):
        messages = []
        for name, member in self.members.items():
            messages.append("%s 352 %s %s %s" % (self.cache.serverprefix, self.cache.nick, self.name, repr(member)))
        messages.append("%s 315 %s %s :End of WHO list" % (self.cache.serverprefix, self.cache.nick, self.name))
        return messages


class QueryBuffer(MessageBuffer):
    def __init__(self, nick, config):
        MessageBuffer.__init__(self, config, config.query_backlog_depth)
        self.nick = nick


class DummyLogger(object):
    def call(self, *args):
        pass


class Cache(object):
    def __init__(self, user):
        self.user = user
        self.server = None
        self.welcome = []
        self.motd = []
        self.mode = []
        self.channels = {}
        self.queries = {}
        self.nick = None
        self.host = None
        # dictionary keyed on client resource, which lists when each resource was last known to be alive.
        self.last_seen = defaultdict(lambda: datetime.fromordinal(1))
        self.shells = {}  # key is resource
        self.logger = {}  # 'configured' loggers; key is channel name
        self.temp_logger = {}  # 'temporary' loggers, created for unconfigured channels and privmsg; deleted after inactivity; key is channel/user name
        self.default_logger = None  # logger base class for newly joined channels and privmsgs

    def set_server(self, server):
        self.server = server
        self.server.cache = self
        self.nick = self.server.config.nick

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

    def dispatch_server_message(self, source, message):
        prefix, code, args = parse_message(message)
        handler = getattr(self, 'handle_server_%s' % code, None)
        if handler:
            return handler(source, message, prefix, code, args)
        print "CACHE UNABLE TO DISPATCH UNKNOWN MESSAGE CODE: %s" % message
        return None

    def process_server_message(self, server, message):
        """ Called with each message from the server server. The message should be parsed, analyzed and possibly added to the cache's data-stores."""
        #print "CACHE RECEIVED: %s" % message
        try:
            self.dispatch_server_message(server, message)
        except Exception:
            import sys
            import traceback
            exc_type, exc_value, exc_traceback = sys.exc_info()
            notice = ""
            lines = ["Exception occured while processing server message: %s" % (message)] + traceback.format_exception(exc_type, exc_value, exc_traceback)
            for line in lines:
                notice += ":thud!cache@th.ud NOTICE %s :%s\n" % (self.nick, line.strip())
            # send out the message to any attached clients for this user.
            # TODO: this probably needs to be limited to clients of this server
            # only.
            # TODO: we should really push all exceptions onto some kind of
            # ExceptionBuffer so that they can be retrieved even if they happen
            # before any client connections
            for client in self.user.clients.values():
                client.sendLine(notice)
            print "\n\n\n\nEXCEPTION!!!"
            print notice
            print "\n\n\n\n"

    def update_last_seen(self, client):
        print "[*] UPDATE LAST_SEEN FOR %s" % client.resource
        self.last_seen[client.resource] = datetime.now()

    def handle_client_message(self, client, message):
        """ Called with each message from the client. The message should be parsed and if the cache can handle the message it should send any responses necessary and return true. If the cache can't handle the message, return false."""
        handled = False
        prefix, code, args = parse_message(message)
        last_seen = self.last_seen[client.resource]
        update_last_seen = True
        if code == "USER":
            print "REGISTERING CLIENT: %s" % (message)
            print "RESOURCE (%s) LAST SEEN AT %s" % (client.resource, last_seen)
            if self.welcome:
                client.sendLine("\n".join(self.welcome))
            if self.motd:
                client.sendLine("\n".join(self.motd))
            if self.mode:
                client.sendLine(self.mode)
            for channel in self.channels.values():
                print "FORCING CLIENT JOIN TO CHANNEL %s" % channel.name
                channel.rejoin(client, last_seen)
            for query in self.queries.values():
                print "FORCING CLIENT JOIN TO QUERY %s" % query.nick
                query.rejoin(client, last_seen)
            handled = True
        elif code in ["QUIT"]:
            # just update last_seen
            handled = True
        elif code in ["PRIVMSG", "NOTICE"]:
            if args[0] in self.channels:
                self.channels[args[0]].add_message(message)
            else:
                nick = args[0]
                if not nick in self.queries:
                    self.queries[nick] = QueryBuffer(nick, self.server.config)
                print "QUERY SEND [%s] %s" % (nick, message)
                self.queries[nick].add_message(message)
            # make sure all other connected clients see this message
            message_with_prefix = "%s %s" % (make_prefix(self.nick, self.host), message)
            for c in self.user.clients.values():
                if c != client:
                    c.sendLine(message_with_prefix)
        elif code == "PONG":
            pass
        elif code == "NICK":
            #self.nick = args[0]
            update_last_seen = False
        elif code == "THUD":
            if not client.resource in self.shells:
                self.shells[client.resource] = thudshell.ThudShell(self, client)
            self.shells[client.resource].handle(args)
            handled = True
        elif code == "JOIN":
            chans = args[0].split(", ")
            print "GOT JOIN MESSAGE FOR %s" % chans
            handled = True
            for chan in chans:
                if not chan in self.channels:
                    print "CACHE INGORING CLIENT JOIN TO UNJOINED CHANNEL: %s " % chan
                    handled = False
                    continue
                channel = self.channels[chan]
                if not channel.is_joined:
                    channel.rejoin(client, last_seen)
        elif code == "MODE" and args[0] in self.channels and len(self.channels[args[0]].mode):
            client.sendLine("\n".join(self.channels[args[0]].mode))
            handled = True
        elif code == "WHO" and args[0] in self.channels:
            channel = self.channels[args[0]]
            if channel.has_who:
                client.sendLine("\n".join(channel.get_who()))
                handled = True
        else:
            print "CACHE IGNORING CLIENT MESSAGE %s:%s" % (code, args)
        if update_last_seen:
            self.update_last_seen(client)
        return handled

    # WELCOME
    def handle_server_RPL_WELCOME(self, source, message, prefix, code, args):
        self.welcome = []
        self.welcome.append(message)
        self.serverprefix = prefix

    def handle_server_welcome_messages(self, source, message, prefix, code, args):
        self.welcome.append(message)
    handle_server_RPL_YOURHOST = handle_server_welcome_messages
    handle_server_RPL_CREATED = handle_server_welcome_messages
    handle_server_RPL_MYINFO = handle_server_welcome_messages
    handle_server_RPL_ISUPPORT = handle_server_welcome_messages

    # MOTD
    def handle_server_RPL_MOTDSTART(self, source, message, prefix, code, args):
        self.motd = []
        self.motd.append(message)

    def handle_server_RPL_MOTD(self, source, message, prefix, code, args):
        self.motd.append(message)

    def handle_server_RPL_ENDOFMOTD(self, source, message, prefix, code, args):
        self.motd.append(message)

    def handle_server_MODE(self, source, message, prefix, code, args):
        if args[0] == self.nick:
            self.mode = message
        else:
            self.channels[args[0]].add_mode(message, prefix, code, args)

    # CHANNEL JOIN
    def handle_server_JOIN(self, source, message, prefix, code, args):
        print "SERVER JOIN: %s" % message
        name = args[0]
        if name not in self.channels:
            config = self.server.config.by_path("channels/name=%s" % name)
            if not config:
                config = self.server.config
            self.channels[name] = ChannelBuffer(name, self, config)
        self.host = host_from_prefix(prefix)
        self.channels[name].add_join(message, prefix, code, args)

    def handle_server_PART(self, source, message, prefix, code, args):
        name = args[0]
        self.channels[name].add_part(message, prefix, code, args)

    def handle_server_RPL_NAMREPLY(self, source, message, prefix, code, args):
        name = args[1] in ["=", "*", "@"] and args[2] or args[1]
        self.channels[name].add_names(message, prefix, code, args)

    def handle_server_RPL_ENDOFNAMES(self, source, message, prefix, code, args):
        self.channels[args[1]].add_names(message, prefix, code, args)

    def handle_server_TOPIC(self, source, message, prefix, code, args):
        self.channels[args[0]].set_topic(message, prefix, code, args)

    # CHANNEL MODE
    def handle_server_RPL_CHANNELMODEIS(self, source, message, prefix, code, args):
        print "CACHEING CHANNEL MODE: %s" % message
        self.channels[args[1]].add_channel_mode(message, prefix, code, args)

    def handle_server_RPL_CREATIONTIME(self, source, message, prefix, code, args):
        self.channels[args[1]].add_channel_mode(message, prefix, code, args)

    # CHANNEL WHO
    def handle_server_RPL_WHOREPLY(self, source, message, prefix, code, args):
        self.channels[args[1]].add_who(message, prefix, code, args)
    handle_server_RPL_ENDOFWHO = handle_server_RPL_WHOREPLY

    # PING
    def handle_server_PING(self, source, message, prefix, code, args):
        source.sendLine("PONG %s" % args[0])

    # NICK
    def handle_server_NICK(self, source, message, prefix, code, args):
        print "SERVER NICK: %s" % message
        old = nick_from_prefix(prefix)
        new = args[0]
        if old == self.nick:
            self.nick = new
        for channel in self.channels.values():
            channel.update_nick(old, new)

    # PRIVMSG
    def handle_server_PRIVMSG(self, source, message, prefix, code, args):
        if args[0] in self.channels:
            self.channels[args[0]].add_message(message)
        else:
            nick = prefix[1:].partition("!")[0]
            if not nick in self.queries:
                self.queries[nick] = QueryBuffer(nick, self.server.config)
            print "QUERY RCV [%s] %s" % (nick, message)
            self.queries[nick].add_message(message)
        #self.get_logger(args[0]).log_priovmsg(timestamp, prefix, args[1])
    handle_server_NOTICE = handle_server_PRIVMSG

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
    'ERR_ALREADYREGISTERED': 462,
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
    'ERR_UNIQOPPRIVSNEEDED': 485,
    'ERR_NOOPERHOST'      : 491,
    'ERR_UMODEUNKNOWNFLAG': 501,
    'ERR_USERSDONTMATCH'  : 502,
}
numeric_codes_reverse = {v: k for k, v in numeric_codes.items()}
# merge into module:
globals().update(numeric_codes)

# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4
