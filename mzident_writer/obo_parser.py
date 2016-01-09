from collections import defaultdict


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
