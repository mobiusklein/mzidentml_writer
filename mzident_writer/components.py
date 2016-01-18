import warnings

from datetime import datetime
from numbers import Number as NumberBase
from itertools import chain
from functools import partial

from . import controlled_vocabulary


from lxml import etree


def make_counter(start=1):
    '''
    Create a functor whose only internal piece of data is a mutable container
    with a reference to an integer, `start`. When the functor is called, it returns
    current `int` value of `start` and increments the mutable value by one.

    Parameters
    ----------
    start: int, optional
        The number to start counting from. Defaults to `1`.

    Returns
    -------
    int:
        The next number in the count progression.
    '''
    start = [start]

    def count_up():
        ret_val = start[0]
        start[0] += 1
        return ret_val
    return count_up


def camelize(name):
    parts = name.split("_")
    if len(parts) > 1:
        return ''.join(parts[0] + [part.title() if part != "ref" else "_ref" for part in parts[1:]])
    else:
        return name


def id_maker(type_name, id_number):
    return "%s_%d" % (type_name.upper(), id_number)


NO_TRACK = object()


class CountedType(type):
    _cache = {}

    def __new__(cls, name, parents, attrs):
        new_type = type.__new__(cls, name, parents, attrs)
        tag_name = attrs.get("tag_name")
        new_type.counter = staticmethod(make_counter())
        if attrs.get("_track") is NO_TRACK:
            return new_type
        cls._cache[name] = new_type
        if tag_name is not None:
            cls._cache[tag_name] = new_type
        return new_type


class TagBase(object):
    __metaclass__ = CountedType

    type_attrs = {}

    def __init__(self, tag_name=None, text="", **attrs):
        self.tag_name = tag_name or self.tag_name
        _id = attrs.pop('id', None)
        self.attrs = {}
        self.attrs.update(self.type_attrs)
        self.text = text
        self.attrs.update(attrs)
        if _id is None:
            self._id_number = self.counter()
            self._id_string = None
        elif isinstance(_id, int):
            self._id_number = _id
            self._id_string = None
        elif isinstance(_id, basestring):
            self._id_number = None
            self._id_string = _id

    def __getattr__(self, key):
        try:
            return self.attrs[key]
        except KeyError:
            try:
                return self.attrs[camelize(key)]
            except KeyError:
                raise AttributeError("%s has no attribute %s" % (self.__class__.__name__, key))

    @property
    def id(self):
        if self._id_string is None:
            self._id_string = id_maker(self.tag_name, self._id_number)
        return self._id_string

    def element(self, xml_file=None, with_id=False):
        attrs = {k: str(v) for k, v in self.attrs.items()}
        if with_id:
            attrs['id'] = self.id
        if xml_file is None:
            return etree.Element(self.tag_name, **attrs)
        else:
            return xml_file.element(self.tag_name, **attrs)

    def write(self, xml_file, with_id=False):
        el = self.element(with_id=with_id)
        xml_file.write(el)

    __call__ = element

    def __repr__(self):
        return "<%s id=\"%s\" %s>" % (self.tag_name, self.id, " ".join("%s=\"%s\"" % (
            k, str(v)) for k, v in self.attrs.items()))

    def __eq__(self, other):
        try:
            return self.attrs == other.attrs
        except AttributeError:
            return False

    def __ne__(self, other):
        try:
            return self.attrs != other.attrs
        except AttributeError:
            return True

    def __hash__(self):
        return hash((self.tag_name, frozenset(self.attrs.items())))


class MzIdentML(TagBase):
    type_attrs = {
        "xmlns": "http://psidev.info/psi/pi/mzIdentML/1.1",
        "version": "1.1.0",
        "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
        "xsi:schemaLocation": "http://psidev.info/psi/pi/mzIdentML/1.1 ../../schema/mzIdentML1.1.0.xsd"
    }

    def __init__(self, **attrs):
        attrs.setdefault('creationDate', datetime.utcnow())
        super(MzIdentML, self).__init__("MzIdentML", **attrs)


class CVParam(TagBase):
    tag_name = "cvParam"

    @classmethod
    def param(cls, name, value=None):
        if isinstance(name, cls):
            return name.write
        else:
            if value is None:
                return cls(name=name).write
            else:
                return cls(name=name, value=value).write

    def __init__(self, accession=None, name=None, ref=None, value=None, **attrs):
        if ref is not None:
            attrs["cvRef"] = ref
        if accession is not None:
            attrs["accession"] = accession
        if name is not None:
            attrs["name"] = name
        if value is not None:
            attrs['value'] = value
        super(CVParam, self).__init__(self.tag_name, **attrs)
        self.patch_accession(accession, ref)

    @property
    def value(self):
        return self.attrs.get("value")

    @value.setter
    def value(self, value):
        self.attrs['value'] = value

    @property
    def ref(self):
        return self.attrs['cvRef']

    @property
    def name(self):
        return self.attrs['name']

    @property
    def accession(self):
        return self.attrs['accession']

    def __call__(self, *args, **kwargs):
        self.write(*args, **kwargs)

    def patch_accession(self, accession, ref):
        if accession is not None:
            if isinstance(accession, int):
                accession = "%s:%d" % (ref, accession)
                self.attrs['accession'] = accession
            else:
                self.attrs['accession'] = accession


class UserParam(CVParam):
    tag_name = "userParam"


class CV(TagBase):
    tag_name = 'cv'

    def __init__(self, id, uri, **kwargs):
        super(CV, self).__init__(id=id, uri=uri, **kwargs)
        self._vocabulary = None

    def load(self, handle=None):
        if handle is None:
            fp = controlled_vocabulary.obo_cache.resolve(self.uri)
            cv = controlled_vocabulary.ControlledVocabulary.from_obo(fp)
        else:
            cv = controlled_vocabulary.ControlledVocabulary.from_obo(handle)
        try:
            cv.id = self.id
        except:
            pass
        return cv

    def __getitem__(self, key):
        if self._vocabulary is None:
            self._vocabulary = self.load()
        return self._vocabulary[key]


class ProvidedCV(CV):
    _track = NO_TRACK

    def __init__(self, id, uri, **kwargs):
        super(ProvidedCV, self).__init__(id, uri, **kwargs)
        self._provider = None

    def load(self, handle=None):
        cv = controlled_vocabulary.obo_cache.resolve(self.uri)
        try:
            cv.id = self.id
        except:
            pass
        return cv

    def __getitem__(self, key):
        if self._provider is None:
            self._provider = self.load()
        return self._provider[key]


def _make_tag_type(name, **attrs):
    return type(name, (TagBase,), {"tag_name": name, "type_attrs": attrs})


def _element(_tag_name, *args, **kwargs):
    try:
        eltype = CountedType._cache[_tag_name]
    except KeyError:
        eltype = _make_tag_type(_tag_name)
    return eltype(*args, **kwargs)


def element(xml_file, _tag_name, *args, **kwargs):
    with_id = kwargs.pop("with_id", False)
    if isinstance(_tag_name, basestring):
        el = _element(_tag_name, *args, **kwargs)
    else:
        el = _tag_name
    return el.element(xml_file=xml_file, with_id=with_id)


default_cv_list = [
    _element(
        "cv", id="PSI-MS",
        uri=("http://psidev.cvs.sourceforge.net/viewvc/*checkout*/psidev"
             "/psi/psi-ms/mzML/controlledVocabulary/psi-ms.obo"),
        version="2.25.0", fullName="PSI-MS"),
    _element(
        "cv", id="UO",
        uri="http://obo.cvs.sourceforge.net/*checkout*/obo/obo/ontology/phenotype/unit.obo",
        fullName="UNIT-ONTOLOGY"),
    ProvidedCV(id="UNIMOD", uri="http://www.unimod.org/obo/unimod.obo", fullName="UNIMOD")
]


common_units = {
    "parts per million": "UO:0000169",
    "dalton": "UO:0000221"
}


class ChildTrackingMeta(type):
    def __new__(cls, name, parents, attrs):
        if not hasattr(cls, "_cache"):
            cls._cache = dict()
        new_type = type.__new__(cls, name, parents, attrs)
        cls._cache[name] = new_type
        return new_type


class SpecializedContextCache(dict):
    def __init__(self, type_name):
        self.type_name = type_name

    def __getitem__(self, key):
        try:
            item = dict.__getitem__(self, key)
            return item
        except KeyError:
            warnings.warn("No reference was found for %d in %s" % (key, self.type_name), stacklevel=3)
            new_value = id_maker(self.type_name, key)
            self[key] = new_value
            return new_value

    def __repr__(self):
        return '%s\n%s' % (self.type_name, dict.__repr__(self))


class VocabularyResolver(object):
    def __init__(self, vocabularies=None):
        if vocabularies is None:
            vocabularies = default_cv_list
        self.vocabularies = vocabularies

    def param(self, name, value=None, cv_ref=None, **kwargs):
        accession = kwargs.get("accession")
        if isinstance(name, CVParam):
            return name
        else:
            if cv_ref is None:
                for cv in self.vocabularies:
                    try:
                        term = cv[name]
                        name = term["name"]
                        accession = term["id"]
                        cv_ref = cv.id
                    except:
                        pass
            if cv_ref is None:
                return UserParam(name=name, value=value, **kwargs)
            else:
                return CVParam(name=name, accession=accession, value=value, ref=cv_ref, **kwargs)

    def term(self, name):
        for cv in self.vocabularies:
            try:
                term = cv[name]
                return term
            except:
                pass
        else:
            raise KeyError(name)


class DocumentContext(dict, VocabularyResolver):
    def __init__(self, vocabularies=None):
        dict.__init__(self)
        VocabularyResolver.__init__(self, vocabularies)

    def __missing__(self, key):
        self[key] = SpecializedContextCache(key)
        return self[key]

NullMap = DocumentContext()


class ReprBorrowingPartial(partial):
    """
    Create a partial instance that uses the wrapped callable's
    `__repr__` method instead of a generic partial
    """
    def __init__(self, func, *args, **kwargs):
        super(ReprBorrowingPartial, self).__init__(func, *args, **kwargs)

    def __repr__(self):
        return repr(self.func)


class ComponentDispatcher(object):
    """
    A container for a :class:`DocumentContext` which provides
    an automatically parameterized version of all :class:`ComponentBase`
    types which use this instance's context.

    Attributes
    ----------
    context : :class:`DocumentContext`
        The mapping responsible for managing the global
        state of all created components.
    """
    def __init__(self, context=None, vocabularies=None):
        if context is None:
            context = DocumentContext(vocabularies=vocabularies)
        else:
            if vocabularies is not None:
                context.vocabularies.extend(vocabularies)
        self.context = context

    def __getattr__(self, name):
        """
        Provide access to an automatically parameterized
        version of all :class:`ComponentBase` types which
        use this instance's context.

        Parameters
        ----------
        name : str
            Component Name

        Returns
        -------
        ReprBorrowingPartial
            A partially parameterized instance constructor for
            the :class:`ComponentBase` type requested.
        """
        component = ChildTrackingMeta._cache[name]
        return ReprBorrowingPartial(component, context=self.context)

    def register(self, entity_type, id):
        """
        Pre-declare an entity in the document context. Ensures that
        a reference look up will be satisfied.

        Parameters
        ----------
        entity_type : str
            An entity type, either a tag name or a component name
        id : int
            The unique id number for the thing registered

        Returns
        -------
        str
            The constructed reference id
        """
        value = id_maker(entity_type, id)
        self.context[entity_type][id] = value
        return value

    @property
    def vocabularies(self):
        return self.context.vocabularies

    def param(self, *args, **kwargs):
        return self.context.param(*args, **kwargs)

    def term(self, *args, **kwargs):
        return self.context.term(*args, **kwargs)

# ------------------------------------------
# Base Component Definitions


class ComponentBase(object):
    __metaclass__ = ChildTrackingMeta

    def __init__(self, *args, **kwargs):
        pass

    def __getattr__(self, key):
        try:
            return self.element.attrs[key]
        except KeyError:
            raise AttributeError(key)

    def write(self, xml_file):
        raise NotImplementedError()

    def __call__(self, xml_file):
        self.write(xml_file)


class GenericCollection(ComponentBase):
    def __init__(self, tag_name, members, context=NullMap):
        self.members = members
        self.tag_name = tag_name
        self.element = _element(tag_name, xmlns="http://psidev.info/psi/pi/mzIdentML/1.1")

    def write(self, xml_file):
        with self.element.element(xml_file, with_id=False):
            for member in self.members:
                member.write(xml_file)


class IDGenericCollection(GenericCollection):
    def __init__(self, tag_name, members, id, context=NullMap):
        self.members = members
        self.tag_name = tag_name
        self.element = _element(tag_name, xmlns="http://psidev.info/psi/pi/mzIdentML/1.1", id=id)
        context[tag_name][id] = self.element.id

    def write(self, xml_file):
        with self.element.element(xml_file, with_id=True):
            for member in self.members:
                member.write(xml_file)

# --------------------------------------------------
# Input File Information


class SourceFile(ComponentBase):
    def __init__(self, location, file_format, id=None, context=NullMap):
        self.file_format = file_format
        self.element = _element("SourceFile", location=location, id=id)
        self.context = context
        context["SourceFile"][id] = self.element.id

    def write(self, xml_file):
        with self.element.element(xml_file, with_id=True):
            with element(xml_file, "FileFormat"):
                self.context.param(self.file_format)(xml_file)


class SearchDatabase(ComponentBase):
    def __init__(self, name, file_format, location=None, id=None, context=NullMap):
        self.location = location
        self.file_format = file_format
        self.element = _element("SearchDatabase", location=location, name=name, id=id)
        context["SearchDatabase"][id] = self.element.id
        self.context = context

    def write(self, xml_file):
        with self.element.element(xml_file, with_id=True):
            with element(xml_file, "FileFormat"):
                self.context.param(self.file_format)(xml_file)
            with element(xml_file, "DatabaseName"):
                UserParam(name=self.name).write(xml_file)


class SpectraData(ComponentBase):
    def __init__(self, location, file_format, spectrum_id_format, id=None, context=NullMap):
        self.file_format = file_format
        self.spectrum_id_format = spectrum_id_format
        self.element = _element("SpectraData", id=id, location=location)
        context['SpectraData'][id] = self.element.id
        self.context = context

    def write(self, xml_file):
        with self.element.element(xml_file, with_id=True):
            with element(xml_file, "FileFormat"):
                self.context.param(self.file_format)(xml_file)
            with element(xml_file, "SpectrumIDFormat"):
                self.context.param(self.spectrum_id_format)(xml_file)


class Inputs(GenericCollection):
    def __init__(self, source_files=tuple(), search_databases=tuple(), spectra_data=tuple(), context=NullMap):
        items = list()
        items.extend(source_files)
        items.extend(search_databases)
        items.extend(spectra_data)
        super(Inputs, self).__init__("Inputs", items, context=context)

# --------------------------------------------------
# Identification Information


class DBSequence(ComponentBase):
    def __init__(self, accession, sequence, id, search_database_id=1, context=NullMap):
        self.sequence = sequence
        self.search_database_ref = context['SearchDatabase'][search_database_id]
        self.element = _element(
            "DBSequence", accession=accession, id=id,
            length=len(sequence), searchDatabase_ref=self.search_database_ref)

        context["DBSequence"][id] = self.element.id

    def write(self, xml_file):
        protein = self.sequence
        with self.element.element(xml_file, with_id=True):
            with element(xml_file, "Seq"):
                xml_file.write(protein)


class Peptide(ComponentBase):
    def __init__(self, peptide_sequence, id, modifications=tuple(), context=NullMap):
        self.peptide_sequence = peptide_sequence
        self.modifications = modifications
        self.element = _element("Peptide", id=id)
        context["Peptide"][id] = self.element.id

    def write(self, xml_file):
        with self.element.element(xml_file, with_id=True):
            with element(xml_file, "PeptideSequence"):
                xml_file.write(self.peptide_sequence)
            for mod in self.modifications:
                mod.write(xml_file)


class PeptideEvidence(ComponentBase):
    def __init__(self, peptide_id, db_sequence_id, id, start_position, end_position,
                 is_decoy=False, pre='', post='', context=NullMap):
        self.peptide_id = peptide_id
        self.db_sequence_id = db_sequence_id
        self.element = _element(
            "PeptideEvidence", isDecoy=is_decoy, start=start_position,
            end=end_position, peptide_ref=context["Peptide"][peptide_id],
            dBSequence_ref=context['DBSequence'][db_sequence_id],
            pre=pre, post=post, id=id)
        context["PeptideEvidence"][id] = self.element.id

    def write(self, xml_file):
        xml_file.write(self.element(with_id=True))


class SpectrumIdentificationResult(ComponentBase):
    def __init__(self, spectra_data_id, spectrum_id, id=None, identifications=tuple(), context=NullMap):
        self.identifications = identifications
        self.element = _element(
            "SpectrumIdentificationResult", spectraData_ref=context["SpectraData"][spectra_data_id],
            spectrumID=spectrum_id, id=id)

    def write(self, xml_file):
        with self.element.element(xml_file, with_id=True):
            for item in self.identifications:
                item.write(xml_file)


class SpectrumIdentificationItem(ComponentBase):
    def __init__(self, calculated_mass_to_charge, experimental_mass_to_charge,
                 charge_state, peptide_id, peptide_evidence_id, score, id, cv_params=None,
                 pass_threshold=True, rank=1, context=NullMap):
        self.peptide_evidence_ref = context["PeptideEvidence"][peptide_evidence_id]
        self.cv_params = cv_params
        self.score = score

        self.element = _element(
            "SpectrumIdentificationItem", calculatedMassToCharge=calculated_mass_to_charge, chargeState=charge_state,
            experimentalMassToCharge=experimental_mass_to_charge, id=id, passThreshold=pass_threshold,
            peptide_ref=context['Peptide'][peptide_id]
            )
        context['SpectrumIdentificationItem'][id] = self.element.id
        self.context = context

    def write(self, xml_file):
        with self.element.element(xml_file, with_id=True):
            _element(
                "PeptideEvidenceRef",
                peptideEvidence_ref=self.peptide_evidence_ref).write(
                xml_file)
            if isinstance(self.score, CVParam):
                self.score.write(xml_file)
            else:
                self.context.param(name="score", value=self.score)(xml_file)
            for cvp in self.cv_params:
                self.context.param(cvp)(xml_file)


class SpectrumIdentificationList(IDGenericCollection):
    def __init__(self, identification_results, id, context=NullMap):
        super(SpectrumIdentificationList, self).__init__(
            "SpectrumIdentificationList", identification_results, id, context=context)


class AnalysisData(GenericCollection):
    def __init__(self, identification_lists=tuple(), protein_detection_lists=tuple(), context=NullMap):
        items = list()
        items.extend(identification_lists)
        items.extend(protein_detection_lists)
        super(AnalysisData, self).__init__("AnalysisData", items, context)


# --------------------------------------------------
# Meta-collections


class DataCollection(GenericCollection):
    def __init__(self, inputs, analysis_data, context=NullMap):
        super(DataCollection, self).__init__("DataCollection", [inputs, analysis_data], context)


class SequenceCollection(GenericCollection):
    def __init__(self, db_sequences, peptides, peptide_evidence, context=NullMap):
        super(SequenceCollection, self).__init__("SequenceCollection", chain.from_iterable(
            [db_sequences, peptides, peptide_evidence]))


# --------------------------------------------------
# Software Execution Protocol Information


class Enzyme(ComponentBase):
    def __init__(self, name, missed_cleavages=1, id=None, semi_specific=False, site_regexp=None, context=NullMap):
        self.name = name
        if site_regexp is None:
            term = context.term(name)
            try:
                regex_ref = term['has_regexp']
                regex_ent = context.term(regex_ref)
                regex = regex_ent['name']
                site_regexp = regex
            except:
                pass
        self.site_regexp = site_regexp
        self.element = _element(
            "Enzyme", semiSpecific=semi_specific, missedCleavages=missed_cleavages,
            id=id)
        context["Enzyme"][id] = self.element.id
        self.context = context

    def write(self, xml_file):
        with self.element.element(xml_file, with_id=True):
            if self.site_regexp is not None:
                regex = _element("SiteRegexp").element()
                regex.text = etree.CDATA(self.site_regexp)
                xml_file.write(regex)
            with element(xml_file, "EnzymeName"):
                self.context.param(self.name)(xml_file)


class _Tolerance(ComponentBase):

    def __init__(self, low, high=None, unit="parts per million", context=NullMap):
        if isinstance(low, NumberBase):
            low = CVParam(
                accession="MS:1001413", ref="PSI-MS", unitCvRef="UO", unitName=unit,
                unitAccession=common_units[unit], value=low,
                name="search tolerance minus value")
        if high is None:
            high = CVParam(
                accession="MS:1001412", ref="PSI-MS", unitCvRef="UO", unitName=unit,
                unitAccession=common_units[unit], value=low.value,
                name="search tolerance plus value")
        elif isinstance(high, NumberBase):
            high = CVParam(
                accession="MS:1001412", ref="PSI-MS", unitCvRef="UO", unitName=unit,
                unitAccession=common_units[unit], value=high,
                name="search tolerance plus value")

        self.low = low
        self.high = high

    def write(self, xml_file):
        with element(xml_file, self.tag_name):
            self.low.write(xml_file)
            self.high.write(xml_file)


class FragmentTolerance(_Tolerance):
    tag_name = "FragmentTolerance"


class ParentTolerance(_Tolerance):
    tag_name = "ParentTolerance"


class Threshold(ComponentBase):
    no_threshold = CVParam(accession="MS:1001494", ref="PSI-MS", name="no threshold")

    def __init__(self, name=None, context=NullMap):
        if name is None:
            name = self.no_threshold
        self.name = name
        self.context = context

    def write(self, xml_file):
        with element(xml_file, "Threshold"):
            self.context.param(self.name)(xml_file)


class SpectrumIdentificationProtocol(ComponentBase):
    def __init__(self, search_type, analysis_software_id=1, id=1, additional_search_params=tuple(),
                 modification_params=tuple(), enzymes=tuple(), fragment_tolerance=None, parent_tolerance=None,
                 threshold=None, context=NullMap):
        if threshold is None:
            threshold = Threshold(context=context)
        self.parent_tolerance = parent_tolerance
        self.fragment_tolerance = fragment_tolerance
        self.threshold = threshold
        self.enzymes = enzymes
        self.modification_params = modification_params
        self.additional_search_params = additional_search_params
        self.search_type = search_type

        self.element = _element(
            "SpectrumIdentificationProtocol", id=id,
            analysisSoftware_ref=context['AnalysisSoftware'][analysis_software_id])
        context["SpectrumIdentificationProtocol"][id] = self.element.id

        self.context = context

    def write(self, xml_file):
        with self.element(xml_file, with_id=True):
            with element(xml_file, "SearchType"):
                self.context.param(self.search_type)(xml_file)
            with element(xml_file, "AdditionalSearchParams"):
                for search_param in self.additional_search_params:
                    self.contex.param(search_param)(xml_file)
            with element(xml_file, "ModificationParams"):
                for mod in self.modification_params:
                    mod.write(xml_file)
            with element(xml_file, "Enzymes"):
                for enzyme in self.enzymes:
                    enzyme.write(xml_file)
            if self.fragment_tolerance is not None:
                self.fragment_tolerance.write(xml_file)
            if self.parent_tolerance is not None:
                self.parent_tolerance.write(xml_file)
            self.threshold.write(xml_file)


class ProteinDetectionProtocol(ComponentBase):
    def __init__(self, id=1, analysis_software_id=1, threshold=None, context=NullMap):
        if threshold is None:
            threshold = Threshold(context=context)
        self.analysis_software_id = analysis_software_id
        self.element = _element(
            "ProteinDetectionProtocol", id=id,
            analysisSoftware_ref=context["AnalysisSoftware"][analysis_software_id])
        context["ProteinDetectionProtocol"][id] = self.element.id

    def write(self, xml_file):
        with self.element.element(xml_file, with_id=True):
            self.threshold.write(xml_file)


class AnalysisProtocolCollection(GenericCollection):
    def __init__(self, spectrum_identification_protocols=tuple(),
                 protein_detection_protocols=tuple(), context=NullMap):
        items = list()
        items.extend(spectrum_identification_protocols)
        items.extend(protein_detection_protocols)
        super(AnalysisProtocolCollection, self).__init__(self, items, context)


# --------------------------------------------------
# Analysis Collection - Data-to-Analysis

class SpectrumIdentification(ComponentBase):
    def __init__(self, spectra_data_ids_used=None, search_database_ids_used=None, spectrum_identification_list_id=1,
                 spectrum_identification_protocol_id=1, id=1, context=NullMap):
        self.spectra_data_ids_used = [context["SpectraData"][x] for x in (spectra_data_ids_used or [])]
        self.search_database_ids_used = [context["SpectraData"][x] for x in (search_database_ids_used or [])]

        self.element = _element(
            "SpectrumIdentification", id=id,
            spectrumIdentificationList_ref=context["SpectrumIdentificationList"][
                spectrum_identification_list_id],
            spectrumIdentificationProtocol_ref=context["SpectrumIdentificationProtocol"][
                spectrum_identification_protocol_id])
        context["SpectrumIdentification"] = self.element.id

    def write(self, xml_file):
        with self.element(xml_file, with_id=True):
            for spectra_data_id in self.spectra_data_ids_used:
                _element("InputSpectra", spectraData_ref=spectra_data_id).write(xml_file)
            for spearch_database_id in self.search_database_ids_used:
                _element("SearchDatabaseRef", searchDatabase_ref=spectra_data_id).write(xml_file)


# --------------------------------------------------
# Misc. Providence Management


DEFAULT_CONTACT_ID = "PERSON_DOC_OWNER"
DEFAULT_ORGANIZATION_ID = "ORG_DOC_OWNER"


class CVList(ComponentBase):
    def __init__(self, cv_list=None, context=NullMap):
        if cv_list is None:
            cv_list = default_cv_list
        self.cv_list = cv_list

    def write(self, xml_file):
        with element(xml_file, 'cvList'):
            for member in self.cv_list:
                xml_file.write(member.element(with_id=True))


class AnalysisSoftware(ComponentBase):
    def __init__(self, name, id=1, version=None, uri=None, contact=DEFAULT_CONTACT_ID, context=NullMap, **kwargs):
        self.name = name
        self.version = version
        self.uri = uri
        self.contact = contact
        self.kwargs = kwargs
        self.element = _element("AnalysisSoftware", id=id, name=self.name, version=self.version, uri=self.uri)
        context["AnalysisSoftware"][id] = self.element.id

    def write(self, xml_file):
        with self.element(xml_file, with_id=True):
            with element(xml_file, "ContactRole", contact_ref=self.contact):
                with element(xml_file, "Role"):
                    xml_file.write(CVParam(accession="MS:1001267", name="software vendor", cvRef="PSI-MS").element())


class Provider(ComponentBase):
    def __init__(self, id="PROVIDER", contact=DEFAULT_CONTACT_ID, context=NullMap):
        self.id = id
        self.contact = contact

    def write(self, xml_file):
        with element(xml_file, "Provider", id=self.id, xmlns="http://psidev.info/psi/pi/mzIdentML/1.1"):
            with element(xml_file, "ContactRole", contact_ref=self.contact):
                with element(xml_file, "Role"):
                    xml_file.write(CVParam(accession="MS:1001271", name="researcher", cvRef="PSI-MS").element())


class Person(ComponentBase):
    def __init__(self, first_name='first_name', last_name='last_name', id=DEFAULT_CONTACT_ID,
                 affiliation=DEFAULT_ORGANIZATION_ID, context=NullMap):
        self.first_name = first_name
        self.last_name = last_name
        self.id = id
        self.affiliation = affiliation
        self.element = _element("Person", firstName=first_name, last_name=last_name, id=id)
        context["Person"][id] = self.element.id

    def write(self, xml_file):
        with self.element.element(xml_file, with_id=True):
            element(xml_file, 'Affiliation', organization_ref=self.affiliation)


class Organization(ComponentBase):
    def __init__(self, name="name", id=DEFAULT_ORGANIZATION_ID, context=NullMap):
        self.name = name
        self.id = id
        self.element = _element("Organization", name=name, id=id)
        context["Organization"][id] = self.id

    def write(self, xml_file):
        xml_file.write(self.element.element())


DEFAULT_PERSON = Person()
DEFAULT_ORGANIZATION = Organization()


class AuditCollection(ComponentBase):
    def __init__(self, persons=None, organizations=None, context=NullMap):
        if persons is None:
            persons = (DEFAULT_PERSON,)
        if organizations is None:
            organizations = (DEFAULT_ORGANIZATION,)
        self.persons = persons
        self.organizations = organizations

    def write(self, xml_file):
        with element(xml_file, "AuditCollection", xmlns="http://psidev.info/psi/pi/mzIdentML/1.1"):
            for person in self.persons:
                person.write(xml_file)
            for organization in self.organizations:
                organization.write(xml_file)
