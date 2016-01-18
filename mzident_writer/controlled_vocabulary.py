import os
import re

from collections import defaultdict
from urllib2 import urlopen
from . import unimod


class Reference(object):
    def __init__(self, accession, comment=None):
        self.accession = accession
        self.comment = comment

    def __eq__(self, other):
        try:
            return self.accession == other.accession
        except AttributeError:
            return self.accession == other

    def __ne__(self, other):
        return not (self.accession == other.accession)

    def __repr__(self):
        return "%s ! %s" % (self.accession, self.comment)

    def __hash__(self):
        return hash(self.accession)

    @classmethod
    def fromstring(cls, string):
        try:
            accession, comment = map(lambda s: s.strip(), string.split("!"))
            return cls(accession, comment)
        except:
            return cls(string)


class Relationship(object):
    def __init__(self, predicate, accession, comment=None):
        self.predicate = predicate
        self.accession = accession
        self.comment = comment

    def __eq__(self, other):
        try:
            return self.accession == other.accession
        except AttributeError:
            return self.accession == other

    def __ne__(self, other):
        return not (self.accession == other.accession)

    def __repr__(self):
        return "%s ! %s" % (self.accession, self.comment)

    def __hash__(self):
        return hash(self.accession)

    @classmethod
    def fromstring(cls, string):
        groups = re.search(r"(?P<predicate>\S+):?\s(?P<accession>\S+)\s(?:!\s(?P<comment>.*))", string).groupdict()
        return cls(**groups)


class OBOParser(object):
    def __init__(self, handle):
        self.handle = handle
        self.terms = {}
        self.current_term = None
        self.parse()

    def pack(self):
        if self.current_term is None:
            return
        entity = {k: v[0] if len(v) == 1 else v for k, v in self.current_term.items()}
        try:
            is_as = entity['is_a']
            if isinstance(is_as, basestring):
                is_as = Reference.fromstring(is_as)
            else:
                is_as = map(Reference.fromstring, is_as)
            entity['is_a'] = is_as
        except KeyError:
            pass
        try:
            relationships = entity['relationship']
            if not isinstance(relationships, list):
                relationships = [relationships]
            relationships = [Relationship.fromstring(r) for r in relationships]
            for rel in relationships:
                entity[rel.predicate] = rel
        except KeyError:
            pass
        self.terms[entity['id']] = entity
        self.current_term = None

    def parse(self):
        for line in self.handle:
            line = line.strip()
            if not line:
                continue
            elif line == "[Typedef]":
                if self.current_term is not None:
                    self.pack()
                self.current_term = None
            elif line == "[Term]":
                if self.current_term is not None:
                    self.pack()
                self.current_term = defaultdict(list)
            else:
                if self.current_term is None:
                    continue
                key, sep, val = line.partition(":")
                self.current_term[key].append(val.strip())
        self.pack()

    def __getitem__(self, key):
        return self.terms[key]

    def __iter__(self):
        return iter(self.terms.items())


class ControlledVocabulary(object):
    @classmethod
    def from_obo(cls, handle):
        parser = OBOParser(handle)
        return cls(parser.terms)

    def __init__(self, terms, id=None):
        self.terms = terms
        self._names = {
            v['name']: v for v in terms.values()
        }
        self._normalized = {
            v['name'].lower(): v['name']
            for v in terms.values()
        }
        self.id = id

    def __getitem__(self, key):
        try:
            return self.terms[key]
        except KeyError, e:
            try:
                return self._names[key]
            except KeyError:
                try:
                    return self._names[self.normalize_name(key)]
                except KeyError, e2:
                    raise KeyError("%s and %s were not found." % (e, e2))

    def __iter__(self):
        return iter(self.terms)

    def keys(self):
        return self.terms.keys()

    def names(self):
        return self._names.keys()

    def items(self):
        return self.terms.items()

    def normalize_name(self, name):
        return self._normalized[name.lower()]


class OBOCache(object):
    def __init__(self, cache_path='.obo_cache', enabled=True, resolvers=None):
        self.cache_path = cache_path
        self.cache_exists = os.path.exists(cache_path)
        self.enabled = enabled
        self.resolvers = resolvers or {}

    def path_for(self, name, setext=True):
        if not self.cache_exists:
            os.makedirs(self.cache_path)
            self.cache_exists = True
        name = os.path.basename(name)
        if not name.endswith(".obo") and setext:
            name += '.obo'
        return os.path.join(self.cache_path, name)

    def resolve(self, uri):
        if uri in self.resolvers:
            return self.resolvers[uri](self)
        if self.enabled:
            name = self.path_for(uri)
            if os.path.exists(name):
                return open(name)
            else:
                f = urlopen(uri)
                if f.getcode() != 200:
                    raise ValueError("%s did not resolve" % uri)
                with open(name, 'wb') as cache_f:
                    for line in f:
                        cache_f.write(line)
                return open(name)
        else:
            return urlopen(uri)

    def set_resolver(self, uri, provider):
        self.resolvers[uri] = provider

    def __repr__(self):
        return "OBOCache(cache_path=%r, enabled=%r, resolvers=%s)" % (
            self.cache_path, self.enabled, self.resolvers)


def _make_relative_sqlite_sqlalchemy_uri(path):
    return "sqlite:///%s" % path


def resolve_unimod(cache):
    if cache.enabled:
        path = _make_relative_sqlite_sqlalchemy_uri(
            cache.path_for("unimod.db", False))
        return unimod.Unimod(path)
    else:
        return unimod.Unimod()


obo_cache = OBOCache()
obo_cache.set_resolver("http://www.unimod.org/obo/unimod.obo", resolve_unimod)
