# Fiches de décision (ADR)

Une fiche par décision structurante : contexte, décision, alternatives écartées, conséquences. Une décision n'est jamais modifiée : on la remplace par une nouvelle fiche qui la cite.

| N° | Décision | Statut |
|---|---|---|
| [ADR-0001](ADR-0001-monorepo-outillage-et-versions.md) | Monorepo, outillage et versions | acceptée |
| [ADR-0002](ADR-0002-orchestration-rag-interne-plutot-que-llamaindex.md) | Orchestration RAG interne plutôt que LlamaIndex | acceptée |
| [ADR-0003](ADR-0003-file-de-taches-dans-postgresql-pas-de-celery-ni-de-redis.md) | File de tâches dans PostgreSQL (pas de Celery ni de Redis) | acceptée |
| [ADR-0004](ADR-0004-meme-socle-de-donnees-en-desktop-et-en-server.md) | Même socle de données en Desktop et en Server | acceptée |
| [ADR-0005](ADR-0005-repartition-postgresql-qdrant.md) | Répartition PostgreSQL / Qdrant | acceptée |
| [ADR-0006](ADR-0006-modele-de-permissions-cles-d-acces-ferme-par-defaut-verifica.md) | Modèle de permissions : clés d'accès, fermé par défaut, vérification tardive | acceptée |
| [ADR-0007](ADR-0007-recherche-hybride-et-canal-lexical.md) | Recherche hybride et canal lexical | acceptée |
| [ADR-0008](ADR-0008-extraction-bibliotheques-python-tika-pour-les-formats-ancien.md) | Extraction : bibliothèques Python, Tika pour les formats anciens, pas de PyMuPDF | acceptée |
| [ADR-0009](ADR-0009-ocr-rapidocr-modeles-paddleocr-en-onnx.md) | OCR : RapidOCR (modèles PaddleOCR en ONNX) | acceptée |
| [ADR-0010](ADR-0010-generation-locale-ollama-vllm-en-option-serveur.md) | Génération locale : Ollama, vLLM en option serveur | acceptée |
| [ADR-0011](ADR-0011-authentification-et-sessions.md) | Authentification et sessions | acceptée |
| [ADR-0012](ADR-0012-chiffrement-des-secrets.md) | Chiffrement des secrets | acceptée |
| [ADR-0013](ADR-0013-server-avant-desktop.md) | Server avant Desktop | acceptée |
| [ADR-0014](ADR-0014-model-router-bibliotheque-pas-service.md) | Model Router : bibliothèque, pas service | acceptée |
| [ADR-0015](ADR-0015-organisations-org-id-partout-une-seule-organisation-dans-l-i.md) | Organisations : org_id partout, une seule organisation dans l'interface du MVP | acceptée |
| [ADR-0016](ADR-0016-identites-externes-et-correspondance-des-comptes.md) | Identités externes et correspondance des comptes | acceptée |
| [ADR-0017](ADR-0017-ocr-tesseract-par-defaut.md) | OCR : Tesseract par défaut, RapidOCR en alternative (mesuré) | acceptée |

Modèle pour une nouvelle fiche : `ADR-XXXX-titre.md` avec les sections Contexte, Décision, Alternatives écartées, Conséquences.
