import os

import pytest
from urag_connector_local_files import LocalFilesConnector, is_ignored_name
from urag_connectors_base import AccessDeniedError, DocumentRef, NotFoundError


def _tree(tmp_path):
    (tmp_path / "a").mkdir(parents=True)
    (tmp_path / "a" / "contrat.pdf").write_bytes(b"%PDF-1.4 test")
    (tmp_path / "a" / "~$contrat.docx").write_bytes(b"x")
    (tmp_path / "a" / "note.TXT").write_text("bonjour")
    (tmp_path / "archives").mkdir()
    (tmp_path / "archives" / "vieux.txt").write_text("ancien")
    (tmp_path / ".cache").mkdir()
    (tmp_path / ".cache" / "x.txt").write_text("cache")
    (tmp_path / "image.exe").write_bytes(b"MZ")
    (tmp_path / "vide.txt").write_text("")
    return tmp_path


def test_liste_filtre_temporaires_systeme_et_exclusions(tmp_path):
    root = _tree(tmp_path)
    c = LocalFilesConnector({"roots": [str(root)], "exclude_globs": ["archives/*"]})
    names = sorted(d.filename for d in c.list_documents())
    assert names == ["contrat.pdf", "note.TXT"]
    assert c.test_connection().ok


def test_identifiant_stable_et_lecture(tmp_path):
    root = _tree(tmp_path)
    c = LocalFilesConnector({"roots": [str(root)]})
    doc = next(d for d in c.list_documents() if d.filename == "note.TXT")
    fetched = c.fetch_content(doc.ref, tmp_path / "out")
    assert fetched.path.read_text() == "bonjour"
    again = next(d for d in c.list_documents() if d.filename == "note.TXT")
    assert again.ref == doc.ref  # même version tant que le fichier ne change pas
    os.utime(root / "a" / "note.TXT", ns=(1, 1))
    changed = next(d for d in c.list_documents() if d.filename == "note.TXT")
    assert changed.ref.external_id == doc.ref.external_id and changed.ref.version != doc.ref.version


def test_jamais_en_dehors_de_la_racine(tmp_path):
    root = _tree(tmp_path / "racine")
    c = LocalFilesConnector({"roots": [str(root)]})
    with pytest.raises(AccessDeniedError):
        c.fetch_content(DocumentRef(f"{root.resolve().as_posix()}|../../etc/passwd"), tmp_path / "out")
    with pytest.raises(NotFoundError):
        c.fetch_content(DocumentRef("/autre/racine|x.txt"), tmp_path / "out")


def test_liens_symboliques_ignores(tmp_path):
    root = _tree(tmp_path / "racine")
    (tmp_path / "secret.txt").write_text("secret")
    (root / "lien.txt").symlink_to(tmp_path / "secret.txt")
    c = LocalFilesConnector({"roots": [str(root)]})
    assert "lien.txt" not in {d.filename for d in c.list_documents()}


def test_droits_espace_seulement():
    access = LocalFilesConnector({"roots": ["/tmp"]}).get_access([DocumentRef("x")])
    assert access[0].complete and access[0].entries[0].principal == "space"


def test_noms_ignores():
    assert all(is_ignored_name(n) for n in ("~$a.docx", ".~lock.a#", "Thumbs.db", "a.tmp", ".cache"))
    assert not is_ignored_name("rapport.pdf")


def test_racine_hors_des_dossiers_autorises_refusee(tmp_path, monkeypatch):
    allowed = tmp_path / "documents"
    (allowed / "service").mkdir(parents=True)
    monkeypatch.setenv("URAG_LOCAL_FILES_ALLOWED_ROOTS", str(allowed))
    LocalFilesConnector({"roots": [str(allowed / "service")]})  # sous-dossier : accepté
    for root in ("/", "/run", str(tmp_path), str(allowed / ".." / "autre"), str(allowed) + "-voisin"):
        with pytest.raises(AccessDeniedError, match="non autorisé"):
            LocalFilesConnector({"roots": [root]})


def test_lien_symbolique_vers_l_exterieur_refuse(tmp_path, monkeypatch):
    allowed = tmp_path / "documents"
    allowed.mkdir()
    (allowed / "raccourci").symlink_to("/etc")
    monkeypatch.setenv("URAG_LOCAL_FILES_ALLOWED_ROOTS", str(allowed))
    with pytest.raises(AccessDeniedError):
        LocalFilesConnector({"roots": [str(allowed / "raccourci")]})  # résolu avant le contrôle


def test_sans_dossier_autorise_aucune_source_locale(tmp_path, monkeypatch):
    monkeypatch.delenv("URAG_LOCAL_FILES_ALLOWED_ROOTS", raising=False)
    with pytest.raises(AccessDeniedError, match="aucun"):
        LocalFilesConnector({"roots": [str(tmp_path)]})  # fermé par défaut
