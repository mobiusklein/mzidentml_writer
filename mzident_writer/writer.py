from collections import Iterable, Mapping
from contextlib import contextmanager
from .components import (
    ComponentDispatcher, etree, common_units, element, _element,
    id_maker)

try:
    basestring
except:
    basestring = (str, bytes)


def ensure_iterable(obj):
    if not isinstance(obj, Iterable) or isinstance(obj, basestring) or isinstance(obj, Mapping):
        return [obj]
    return obj


class XMLWriterMixin(object):

    @contextmanager
    def element(self, element_name, **kwargs):
        try:
            with element(self.writer, element_name, **kwargs):
                yield
        except AttributeError:
            if self.writer is None:
                raise ValueError("This writer has not yet been created."
                    " Make sure to use this object as a context manager using the "
                    "`with` notation or by explicitly calling its __enter__ and "
                    "__exit__ methods.")
            else:
                raise

    def write(self, *args, **kwargs):
        try:
            self.writer.write(*args, **kwargs)
        except AttributeError:
            if self.writer is None:
                raise ValueError("This writer has not yet been created."
                    " Make sure to use this object as a context manager using the "
                    "`with` notation or by explicitly calling its __enter__ and "
                    "__exit__ methods.")
            else:
                raise


class DocumentSection(ComponentDispatcher, XMLWriterMixin):
    def __init__(self, section, writer, parent_context):
        super(DocumentSection, self).__init__(parent_context)
        self.section = section
        self.writer = writer

    def __enter__(self):
        self.toplevel = element(self.writer, self.section)
        self.toplevel.__enter__()

    def __exit__(self, exc_type, exc_value, traceback):
        self.toplevel.__exit__(exc_type, exc_value, traceback)
        self.writer.flush()


# ----------------------
# Order of Instantiation
# Providence -> Input -> Protocol -> Identification


class MzIdentMLWriter(ComponentDispatcher, XMLWriterMixin):
    """
    A high level API for generating MzIdentML XML files from simple Python objects.

    This class depends heavily on lxml's incremental file writing API which in turn
    depends heavily on context managers. Almost all logic is handled inside a context
    manager and in the context of a particular document. Since all operations assume
    that they have access to a universal identity map for each element in the document,
    that map is centralized in this instance.

    MzIdentMLWriter inherits from :class:`.ComponentDispatcher`, giving it a :attr:`context`
    attribute and access to all `Component` objects pre-bound to that context with attribute-access
    notation.
    
    Attributes
    ----------
    outfile : file
        The open, writable file descriptor which XML will be written to.
    xmlfile : lxml.etree.xmlfile
        The incremental XML file wrapper which organizes file writes onto :attr:`outfile`.
        Kept to control context.
    writer : lxml.etree._IncrementalFileWriter
        The incremental XML writer produced by :attr:`xmlfile`. Kept to control context.
    toplevel : lxml.etree._FileWriterElement
        The top level incremental xml writer element which will be closed at the end
        of file generation. Kept to control context
    context : :class:`.DocumentContext`
    """
    def __init__(self, outfile, **kwargs):
        super(MzIdentMLWriter, self).__init__()
        self.outfile = outfile
        self.xmlfile = etree.xmlfile(outfile, **kwargs)
        self.writer = None
        self.toplevel = None

    def _begin(self):
        self.writer = self.xmlfile.__enter__()

    def __enter__(self):
        self._begin()
        self.toplevel = element(self.writer, "MzIdentML")
        self.toplevel.__enter__()

    def __exit__(self, exc_type, exc_value, traceback):
        self.toplevel.__exit__(exc_type, exc_value, traceback)
        self.writer.flush()
        self.xmlfile.__exit__(exc_type, exc_value, traceback)
        self.outfile.close()

    def close(self):
        self.outfile.close()

    def providence(self, software=tuple(), owner=None, organization=None):
        """
        Write the analysis providence section, a top-level segment of the MzIdentML document

        This section should be written early on to register the list of software used in this
        analysis
        
        Parameters
        ----------
        software : dict or list of dict, optional
            A single dictionary or list of dictionaries specifying an :class:`AnalysisSoftware` instance
        owner : dict, optional
            A dictionary specifying a :class:`Person` instance. If missing, a default person will be created
        organization : dict, optional
            A dictionary specifying a :class:`Organization` instance. If missing, a default organization will be created
        """
        software = [self.AnalysisSoftware(**(s or {})) for s in ensure_iterable(software)]
        owner = self.Person(**(owner or {}))
        organization = self.Organization(**(organization or {}))

        self.GenericCollection("AnalysisSoftwareList", software).write(self.writer)
        self.Provider(contact=owner.id).write(self.writer)
        self.AuditCollection([owner], [organization]).write(self.writer)

    def inputs(self, source_files=tuple(), search_databases=tuple(), spectra_data=tuple()):
        source_files = [self.SourceFile(**(s or {})) for s in source_files]
        search_databases = [self.SearchDatabase(**(s or {})) for s in search_databases]
        spectra_data = [self.SpectraData(**(s or {})) for s in spectra_data]

        self.Inputs(source_files, search_databases, spectra_data).write(self.writer)

    def sequence_collection(self, db_sequences=tuple(), peptides=tuple(), peptide_evidence=tuple()):
        db_sequences = (self.DBSequence(**(s or {})) for s in ensure_iterable(db_sequences))
        peptides = (self.Peptide(**(s or {})) for s in ensure_iterable(peptides))
        peptide_evidence = (self.PeptideEvidence(**(s or {})) for s in ensure_iterable(peptide_evidence))
