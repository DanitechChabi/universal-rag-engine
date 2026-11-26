# syntax=docker/dockerfile:1
# Image du relais HTTPS : Caddy (Apache-2.0) avec l'interface web construite.
# Derrière un proxy d'entreprise : --secret id=extra_ca,src=<certificat de l'autorité du proxy>.
# Images de base surchargeables (miroirs : mirror.gcr.io/library/…, public.ecr.aws/docker/library/…).
ARG NODE_IMAGE=node:22-bookworm-slim
ARG CADDY_IMAGE=caddy:2.10.2-alpine
FROM ${NODE_IMAGE} AS build
WORKDIR /src
COPY pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/
RUN --mount=type=secret,id=extra_ca \
    if [ -s /run/secrets/extra_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/extra_ca; fi \
    && npm install -g pnpm@10.28.0 \
    && pnpm install --frozen-lockfile --filter ./apps/web
COPY apps/web apps/web
RUN pnpm --filter ./apps/web build

FROM ${CADDY_IMAGE}
COPY --from=build /src/apps/web/dist /srv/web
COPY infrastructure/caddy/Caddyfile /etc/caddy/Caddyfile
