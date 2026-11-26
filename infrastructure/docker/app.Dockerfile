# syntax=docker/dockerfile:1
# Image de l'application : API, worker et outil d'administration (urag-admin).
# Construite depuis la racine du dépôt : docker build -f infrastructure/docker/app.Dockerfile .
# Derrière un proxy d'entreprise : --secret id=extra_ca,src=<certificat de l'autorité du proxy>
# (le certificat ne sert qu'aux téléchargements de la construction, il ne reste pas dans l'image).
ARG PYTHON_IMAGE=python:3.12-slim-bookworm
FROM ${PYTHON_IMAGE} AS build
# Environnement créé directement à son emplacement final (chemins des exécutables).
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_PROJECT_ENVIRONMENT=/opt/urag
WORKDIR /src
COPY pyproject.toml uv.lock ./
COPY core core
COPY connectors connectors
COPY services services
# Dépendances de production seulement (le simulateur M-Files est une dépendance de développement).
RUN --mount=type=secret,id=extra_ca \
    if [ -s /run/secrets/extra_ca ]; then export PIP_CERT=/run/secrets/extra_ca SSL_CERT_FILE=/run/secrets/extra_ca; fi \
    && pip install --no-cache-dir uv==0.11.32 \
    && uv sync --frozen --no-dev --no-editable --package urag-api --package urag-worker

FROM ${PYTHON_IMAGE}
# Tesseract (Apache-2.0) : OCR par défaut, ADR-0017. Aucune autre dépendance système.
# (apt lit le certificat facultatif sous un compte non privilégié : copie lisible, supprimée ensuite.)
RUN --mount=type=secret,id=extra_ca \
    if [ -s /run/secrets/extra_ca ]; then \
      cp /run/secrets/extra_ca /tmp/extra_ca.crt && chmod 644 /tmp/extra_ca.crt \
      && printf 'Acquire::https::CaInfo "/tmp/extra_ca.crt";\n' > /etc/apt/apt.conf.d/99extra-ca \
      && sed -i 's#http://deb.debian.org#https://deb.debian.org#g' /etc/apt/sources.list.d/debian.sources; fi \
    && apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-fra tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/* /etc/apt/apt.conf.d/99extra-ca /tmp/extra_ca.crt \
    && sed -i 's#https://deb.debian.org#http://deb.debian.org#g' /etc/apt/sources.list.d/debian.sources \
    && useradd --no-log-init --uid 10001 --home-dir /var/lib/urag --create-home urag \
    && mkdir -p /var/lib/urag/tmp /models && chown -R urag:urag /var/lib/urag
COPY --from=build /opt/urag /opt/urag
COPY database /opt/urag-database
ENV PATH=/opt/urag/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    URAG_DATABASE_DIR=/opt/urag-database \
    URAG_TMP_DIR=/var/lib/urag/tmp \
    URAG_API_HOST=0.0.0.0
USER urag
WORKDIR /var/lib/urag
EXPOSE 8000
CMD ["urag-api"]
