class ThudCommand(object):
    def __init__(self,shell,name,description=""):
        self.shell = shell
        self.name = name
        self.description = description
    def help(self,args):
        self._help(args)
    def _help(self,args):
        self.shell.respond("help: %s" % self.description)
    def run(self, args):
        self._run(args)
    def _run(self, args):
        pass

class HelpCommand(ThudCommand):
    def __init__(self,shell):
        super(HelpCommand,self).__init__(shell,"help","command help")
    def _run(self,args):
        if not len(args):
            self.shell.respond("thud shell help. commands available:")
            for name, cmd  in self.shell.commands.items():
                self.shell.respond("    %s - %s" % (name,cmd.description))
        else:
            cmd = args[0].lower()
            if cmd in self.shell.commands:
                self.shell.commands[cmd].help(args[1:])
            else:
                self.shell.respond("help: unknown command")

class ListCommand(ThudCommand):
    def __init__(self,shell):
        super(ListCommand,self).__init__(shell,"list","list things (servers, client-resources, etc)")
    def _run(self,args):
        if len(args) != 1:
            return self.help(args)
        kind = args[0].lower()
        if "servers".startswith(kind) or "upstreams".startswith(kind):
            self.shell.respond("connected upstream servers:")
            upstream_connections = self.shell.cache.upstream.config.user.upstream_connections
            for name, upstream in upstream_connections.items():
                self.shell.respond("    %s - %s" % (name, upstream.config.uri))
        elif "clients".startswith(kind) or "resources".startswith(kind):
            self.shell.respond("connected downstream client resources:")
            clients = self.shell.cache.upstream.config.user.clients
            for resource, client in clients.items():
                self.shell.respond("    %s connected to %s last seen at %s" % (resource,client.upstreamref,self.shell.cache.last_seen[resource]))


class ThudShell(object):
    def __init__(self, cache, client):
        self.cache,self.client = cache,client
        self.commands = {
            "help": HelpCommand(self),
            "list": ListCommand(self),
        }
    def respond(self, message):
        messages = message.split("\n")
        for m in messages:
            self.client.sendLine(":thud!cache@th.ud NOTICE %s :%s" % (self.cache.upstream.config.nick,m))
    def handle(self, args):
        cmd = args[0].lower()
        if cmd in self.commands:
            self.commands[cmd].run(args[1:])
        else:
            self.respond("unknown command: %s" % args)

