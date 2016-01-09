from mzident_writer import writer

software = [{
    "name": "My Generic Software",
    "version": "1.2.0rc",
    "uri": "http://www.github.com",
}]

mw = writer.MzIdentMLWriter(open("test.mzid", 'wb'))
with mw:
    mw.providence(software=software)