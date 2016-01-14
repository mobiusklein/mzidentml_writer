from lxml import etree
from mzident_writer import writer

software = [{
    "name": "My Generic Software",
    "version": "1.2.0rc",
    "uri": "http://www.github.com",
}]


search_database = {
    "name": "Uniprot Human Proteins",
    "location": "file:///home/user/search_database/UniprotHumanProteins.fa",
    "file_format": "fasta format",
    "id": 1
}

source_file = {
    "location": "file:///home/user/projects/human_protein_analysis",
    "file_format": "data stored in database",
    "id": 1
}

spectra_data = {
    "location": "file:///home/user/datasets/human_protein_analysis/human_qtof.mgf",
    "file_format": "Mascot MGF format",
    "spectrum_id_format": "multiple peak list nativeID format",
    "id": 1
}

proteins = [
    {
        "accession": "P02763|A1AG1_HUMAN",
        "sequence": ("MALSWVLTVLSLLPLLEAQIPLCANLVPVPITNATLDQITGKWFYIASAFRNEEYNKSVQEIQATFFYFTPNKTEDTIFLREYQTRQDQCIYNT"
                     "TYLNVQRENGTISRYVGGQEHFAHLLILRDTKTYMLAFDVNDEKNWGLSVYADKPETTKEQLGEFYEALDCLRIPKSDVVYTDWKKDKCEPLEK"
                     "QHEKERKQEEGES"),
        "id": 1,
        "search_database_id": 1
    }
]

peptides = [
    {
        "id": 1,
        "peptide_sequence": "NEEYNK"
    },
    {
        "id": 2,
        "peptide_sequence": "ENGTISR"
    }
]

peptide_evidence = [
    {
        "is_decoy": False,
        "start_position": 128,
        "end_position": 128 + 6,
        "peptide_id": 1,
        "db_sequence_id": 1,
        "id": 1
    },
    {
        "is_decoy": False,
        "start_position": 228,
        "end_position": 228 + 7,
        "peptide_id": 2,
        "db_sequence_id": 1,
        "id": 2
    }
]

protocol = {
    "enzymes": [{"name": "trypsin", "missed_cleavages": 2}],
    "fragment_tolerance": (10, None, "parts per million"),
    "id": 1
}

analysis = [[spectra_data['id']], [search_database['id']]]


spectrum_identification_list = {
    "id": 1,
    "identification_results": [{
        "spectra_data_id": 1,
        "spectrum_id": 9122,
        "id": 1,
        "identifications": {
            "calculated_mass_to_charge": 775.38243,
            "experimental_mass_to_charge": 775.38243 - (775.38243 * 2e-4),
            "charge_state": 2,
            "peptide_id": 1,
            "peptide_evidence_id": 1,
            "score": 0.9,
            "id": 1
        }
    }]
}


mw = writer.MzIdentMLWriter(open("test.mzid", 'wb'))
with mw:
    mw.controlled_vocabularies()
    mw.providence(software=software)
    mw.register("SpectraData", spectra_data['id'])
    mw.register("SearchDatabase", search_database['id'])
    mw.register("SpectrumIdentificationList", spectrum_identification_list['id'])
    mw.sequence_collection(proteins, peptides, peptide_evidence)
    with mw.element("AnalysisProtocolCollection"):
        mw.spectrum_identification_protocol(**protocol)
    with mw.element("AnalysisCollection"):
        mw.SpectrumIdentification(*analysis).write(mw)
    with mw.element("DataCollection"):
        mw.inputs(source_file, search_database, spectra_data)
        with mw.element("AnalysisData"):
            mw.spectrum_identification_list(**spectrum_identification_list)

s = etree.tostring(etree.parse("test.mzid"), pretty_print=True)
open('test.mzid', 'wb').write(s)
