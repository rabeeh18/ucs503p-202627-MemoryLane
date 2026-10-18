# Builds the Svelte frontend, then serves it with Caddy. Build context is code/src.
FROM node:20 AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./

ARG VITE_API_BASE=/api
ARG VITE_COGNITO_DOMAIN
ARG VITE_COGNITO_CLIENT_ID
ARG VITE_REDIRECT_URI
ARG VITE_LOGOUT_URI
ENV VITE_API_BASE=$VITE_API_BASE \
    VITE_COGNITO_DOMAIN=$VITE_COGNITO_DOMAIN \
    VITE_COGNITO_CLIENT_ID=$VITE_COGNITO_CLIENT_ID \
    VITE_REDIRECT_URI=$VITE_REDIRECT_URI \
    VITE_LOGOUT_URI=$VITE_LOGOUT_URI
RUN test -n "$VITE_COGNITO_DOMAIN" && test -n "$VITE_COGNITO_CLIENT_ID" \
    || (echo "VITE_COGNITO_DOMAIN and VITE_COGNITO_CLIENT_ID must be set in .env" && exit 1)
RUN npm run build

# The browser extension, zipped with manifest.json at the zip root, served as
# /memorylane-extension.zip for the /extension page.
FROM alpine:3.20 AS extension
RUN apk add --no-cache zip
COPY extension/ /extension/
RUN cd /extension && rm -f README.md && test -f manifest.json \
    && zip -r -X -9 /memorylane-extension.zip . \
    && unzip -l /memorylane-extension.zip | grep -q " manifest.json$"

FROM caddy:2
COPY deploy/caddy/Caddyfile /etc/caddy/Caddyfile
COPY --from=frontend /app/frontend/dist /srv
COPY --from=extension /memorylane-extension.zip /srv/memorylane-extension.zip
