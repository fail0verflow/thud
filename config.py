import yaml
class ConfigError(Exception):
    pass
class Config(object):
    def __init__(self,parent=None, data=None,filename=None):
        self._parent = parent
        self._data = data
        self._filename = filename
        if self._filename:
            self.readfile()
        print self._data
        self._children = []
        self._parse()

    def readfile(self):
        with open(self._filename,"rt") as f:
            self._data = yaml.load(f.read())
    def writefile(self,filename=None):
        filename = filename or self._filename
        with open(filename,"wt") as f:
            f.write(yaml.dump(self._emit()))

    def _parse(self):
        """ Parse yaml.load output inserting Config objects as apropriate. """
        for key,value in self._data.items():
            if type(value) == list:
                if self._children != []:
                    raise ConfigError("An item can't have more than one set of children!")
                self._children = [Config(parent=self,data=x) for x in value]
                self._data[key] = self._children
            if type(value) == dict:
                self._data[key] = Config(parent=self,data=value)

    def _emit(self):
        """ Return data structure in format acceptable to yaml.dump. """
        data = {}
        for key,value in self._data.items():
            if type(value) == list:
                data[key] = [x._emit() for x in value]
            elif type(value) == Config:
                data[key] = value._emit()
            else:
                data[key] = value
        return data

    def by_path(self,path):
        if "." in path:
            separator = "."
        elif "/" in path:
            separator = "/"
        else:
            separator = "./" # guaranteed not to be present, but will allow parition to work.
        part, sep, path = path.partition(separator)
        if part in self._data:
            if not path:
                return self._data[part]
            selector,sep,path = path.partition(separator)
            if "=" not in selector:
                raise ConfigError("We need a selector to be able to pick the right child!")
            key,sep,value = selector.partition("=")
            for child in self._children:
                if child._data[key] == value:
                    if path:
                        return child.by_path(path)
                    return child
        return None

    def __getattr__(self, name):
        return self.get_with_fallback(name)
    def __setattr__(self, name, value):
        if name.startswith("_"):
            object.__setattr__(self,name,value)
        else:
            self._data[name] = value

    def get_root(self):
        if not self._parent:
            return self
        return self._parent.get_root()

    def get_with_fallback(self, key,default=None):
        if key in self._data:
            return self._data[key]
        elif self._parent:
            return self._parent.get_with_fallback(key,default)
        return default

    def __repr__(self):
        res = ""
        for k,v in self._data.items():
            if type(v) is list:
                res += "%s: [\n\t" % k
                for v in self._children:
                    v = "\n\t".join(repr(v).split("\n"))
                    res += "{%s},\n\t" % v
                res += "]\n"
            else:
                res += "%s: %s\n" % (k,v)
        return res





x = Config(filename="c1.user")
print "-----"

y = x.by_path("networks/ref=f0f/channels/name=#f0f1")
#print y
#print y.get_root()
x.staatat = 1
print x.staatat
print y.staatat

print
print
print x.networks


# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4
