# ADR-0008 — Extraction : bibliothèques Python, Tika pour les formats anciens, pas de PyMuPDF

- Statut : **acceptée** (phase 0, novembre 2026)
- Références : cahier des charges, `docs/AUDIT_FAISABILITE.md`

## Contexte

Il faut extraire texte, structure, tableaux et numéros de page de nombreux formats (section 5.4), y compris en Desktop où Java est lourd. Le logiciel est vendu : les licences comptent.

## Décision

- PDF : `pypdfium2` (licences permissives) + détection des pages sans texte ⇒ OCR.
- DOCX, XLSX, PPTX : `python-docx`, `openpyxl`, `python-pptx` ; HTML : parseur HTML ; CSV, TXT : lecture directe.
- DOC, XLS, PPT, RTF et formats rares : **Apache Tika** (serveur en conteneur en mode Server ; en Desktop, Java minimal embarqué ou conversion LibreOffice, à arbitrer en phase 6).
- **Interdit** : PyMuPDF (AGPL ou licence commerciale) et toute dépendance AGPL/SSPL dans le produit.

## Alternatives écartées

Tika pour tout (Java obligatoire, structure et pages moins fines) ; Docling ou Unstructured (riches mais lourds ; pourront être évalués pour les tableaux complexes).

## Conséquences

Plusieurs petites bibliothèques à maintenir, mais extraction plus fine et légère ; vérification automatique des licences des dépendances en intégration continue.
