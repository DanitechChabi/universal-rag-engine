from urag_core.chunking import ChunkingProfile, chunk_document
from urag_core.extraction import Block, ExtractedDocument, clean_text, detect_language, extract

from tests.fixtures.documents import CONTRACT_PAGE_1, CONTRACT_PAGE_2, write_blank_pdf, write_docx, write_pdf


def test_pdf_pages_conservees(tmp_path):
    doc = extract(write_pdf(tmp_path / "c.pdf", [CONTRACT_PAGE_1, CONTRACT_PAGE_2]))
    assert doc.page_count == 2
    loyer = [b for b in doc.blocks if "450 000 FCFA" in b.text]
    assert loyer and loyer[0].page == 2
    assert not doc.pages_without_text


def test_pdf_scanne_signale(tmp_path):
    doc = extract(write_blank_pdf(tmp_path / "scan.pdf"))
    assert doc.pages_without_text == [1]
    assert doc.blocks == []
    assert "OCR" in doc.warnings[0]


def test_docx_titres_et_tableau(tmp_path):
    doc = extract(write_docx(tmp_path / "n.docx"))
    kinds = [b.kind for b in doc.blocks]
    assert kinds.count("heading") == 3 and "table" in kinds
    table = next(b for b in doc.blocks if b.kind == "table")
    assert "10 ans | 4 jours" in table.text


def test_decoupage_conserve_sections_et_tableaux(tmp_path):
    doc = extract(write_docx(tmp_path / "n.docx"))
    chunks = chunk_document(doc, ChunkingProfile(max_chars=400, overlap_chars=50))
    table = [c for c in chunks if c.kind == "table"]
    assert len(table) == 1 and "Ancienneté" in table[0].text
    assert table[0].section_path == ("Note de service RH", "Congés annuels")
    teletravail = next(
        c for c in chunks if "Télétravail est autorisé" in c.text or "télétravail est autorisé" in c.text
    )
    assert teletravail.section_path == ("Note de service RH", "Télétravail")
    assert "Congés" not in teletravail.text  # un changement de section coupe le fragment


def test_decoupage_taille_chevauchement_et_pages():
    long = " ".join(f"Phrase numéro {i} du rapport annuel." for i in range(200))
    doc = ExtractedDocument([Block(long, "paragraph", 3), Block("Fin du rapport.", "paragraph", 4)])
    chunks = chunk_document(doc, ChunkingProfile(max_chars=500, overlap_chars=80))
    assert len(chunks) > 5
    assert all(len(c.text) <= 500 + 80 + 10 for c in chunks)
    assert chunks[1].text.startswith("…")  # chevauchement avec le fragment précédent
    assert chunks[0].page_start == 3 and chunks[-1].page_start == chunks[-1].page_end == 4
    assert all(c.page_start == c.page_end for c in chunks)  # jamais à cheval sur deux pages
    assert [c.ordinal for c in chunks] == list(range(len(chunks)))


def test_grand_tableau_repete_l_entete():
    rows = ["Code | Libellé"] + [f"C{i:03d} | Article numéro {i}" for i in range(200)]
    chunks = chunk_document(ExtractedDocument([Block("\n".join(rows), "table")]), ChunkingProfile(max_chars=600))
    assert len(chunks) > 3 and all(c.text.startswith("Code | Libellé") for c in chunks)


def test_nettoyage_et_langue():
    assert clean_text("archi-\nvage  \x00 du  dossier\r\n") == "archivage du dossier"
    assert detect_language("Le loyer mensuel est fixé par le contrat de bail.") == "fr"
    assert detect_language("The monthly rent is set by the lease agreement and the tenant.") == "en"


def test_listes_numerotees_conservees_et_pas_de_fragment_minuscule():
    from urag_core.extraction import _paragraphs

    text = (
        "Adresse : Abidjan\nTél. 01 02\n\n"
        "BANQUES (3)\n1 BANGE BANK BENIN B 0184 P\n2 BANK OF AFRICA B 0061 F\n3 ECOBANK B 0062 G"
    )
    blocks = _paragraphs(text, 1)
    assert "1 BANGE BANK BENIN B 0184 P\n2 BANK OF AFRICA" in blocks[1].text  # une ligne par élément
    assert _paragraphs("le loyer est payé en\n2026 chaque mois", 1)[0].text == "le loyer est payé en 2026 chaque mois"
    long_list = "BANQUES (40)\n" + "\n".join(f"{i} BANQUE NUMERO {i} DU BENIN B 0{i:03d} X" for i in range(1, 41))
    doc = ExtractedDocument(
        [Block("Adresse : Abidjan. Tél. 01 02 03.", "paragraph", 1), Block(long_list, "paragraph", 1)]
    )
    chunks = chunk_document(doc, ChunkingProfile(max_chars=600, overlap_chars=60))
    assert len(chunks[0].text) >= 300  # l'adresse n'est pas isolée dans un fragment minuscule
    assert all(len(c.text) <= 600 + 300 + 70 for c in chunks)
    assert all("\n" in c.text for c in chunks)  # coupé entre deux lignes de la liste


def test_contexte_du_document():
    from urag_core.extraction import document_context

    first = (
        "Avenue Abdoulaye FADIGA\nBP 3108 – Dakar - Sénégal\nTél. (221) 33 839 05 00\n"
        "SITUATION DE LA MICROFINANCE\nDANS L'UMOA AU 31 DECEMBRE 2025\n"
        "L'encours des dépôts collectés s'est accru de 58,4 milliards FCFA."
    )
    ctx = document_context("Publication - Situation de la microfinance à fin décembre 2025", first)
    assert ctx == (
        "Publication - Situation de la microfinance à fin décembre 2025 — "
        "SITUATION DE LA MICROFINANCE DANS L'UMOA AU 31 DECEMBRE 2025"
    )
    assert document_context("Image numérisée", "texte courant sans titre") is None  # titre générique ignoré
    assert document_context("Microsoft Word - Note_de_service.docx", "") == "Note de service"
    assert "@" not in (document_context(None, "E-MAIL : CONTACT@BANQUE.TEST\nRAPPORT ANNUEL 2025") or "")


def test_contexte_en_tete_du_texte_encode():
    from urag_core.chunking import ChunkDraft

    draft = ChunkDraft(0, "Le loyer est de 900 000 FCFA.", "text", ("Article 3",), 1, 1)
    assert draft.embedding_text("bail", "Bail des Pins 2026").startswith("bail — Bail des Pins 2026 > Article 3\n")
    assert draft.embedding_text("bail").startswith("bail > Article 3\n")


def test_sommaires_et_index_reconnus():
    from urag_core.chunking import is_navigational

    toc = (
        "Table of Contents\nExecutive summary ............................................ 1\n"
        "1. Introduction ............................................... 3\n"
        "2. Overview of practices ....................................... 7\n"
        "3. Recommendations ............................................ 27"
    )
    lists = (
        "LISTE DES TABLEAUX\nTableau 14 - Opérations financières des Etats membres de l'UEMOA 41\n"
        "Tableau 15 - Émissions brutes de titres publics sur le marché régional 42\n"
        "Tableau 16 - Taux d'intérêt et de rendement moyens sur le marché 43\n"
        "Tableau 17 - Évolution de la masse monétaire dans l'Union 45"
    )
    table = (
        "BENIN - UTILISATIONS DECLAREES AUX CENTRALES DES RISQUES\n"
        "Agriculture, sylviculture et pêche 43 044 37 393 35 836\n"
        "Commerce de détail 441 714 518 016 553 366\n"
        "Transports, entrepôts et communications 586 496 635 919 646 994\n"
        "TOTAL 549 071 486 555 466 311"
    )
    form = (
        "1.2 - Raison sociale .........................................\n"
        "1.3 - Nom et contact du responsable ..........................\n"
        "1.4 - Swift .................................................\n"
        "Si oui, indiquez la durée de conservation ...... ans."
    )
    prose = (
        "Article 7 - Résiliation.\nLe bail peut être résilié par lettre recommandée.\n"
        "Le préavis est de 3 mois.\nFait à Cotonou."
    )
    assert is_navigational(toc) and is_navigational(lists)
    assert not is_navigational(table)  # lignes de tableau : plusieurs nombres, pas un numéro de page
    assert not is_navigational(form)  # pointillés à remplir, sans numéro de page
    assert not is_navigational(prose)
