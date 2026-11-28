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

# The search model local search runs in the browser (bge-small-en-v1.5, the
# server's model, as ONNX), served at /models/. Weights are data, not code: the
# extension downloads them once and keeps them in the browser's cache.
FROM alpine:3.20 AS models
RUN apk add --no-cache curl
ARG MODEL_REVISION=ea104dacec62c0de699686887e3f920caeb4f3e3
RUN set -e; dir=/models/bge-small-en-v1.5; mkdir -p "$dir/onnx"; \
    base="https://huggingface.co/Xenova/bge-small-en-v1.5/resolve/$MODEL_REVISION"; \
    for f in config.json tokenizer.json tokenizer_config.json special_tokens_map.json onnx/model.onnx; do \
        curl -fsSL -o "$dir/$f" "$base/$f"; \
    done

# The browser extension with its bundled runtimes (Pyodide, the server's saving
# code, transformers.js; see extension/tools/vendor.mjs), zipped with
# manifest.json at the zip root, served as /memorylane-extension.zip.
FROM node:20 AS extension
RUN apt-get update && apt-get install -y --no-install-recommends zip unzip && rm -rf /var/lib/apt/lists/*
WORKDIR /src
COPY backend/ backend/
COPY extension/ extension/
RUN cd extension && npm ci --ignore-scripts && node tools/vendor.mjs \
    && rm -rf node_modules tools package.json package-lock.json README.md \
    && test -f manifest.json && test -f vendor/pyodide/pyodide.mjs \
    && zip -r -X -9 /memorylane-extension.zip . \
    && unzip -l /memorylane-extension.zip | grep -q " manifest.json$"

FROM caddy:2
COPY deploy/caddy/Caddyfile /etc/caddy/Caddyfile
COPY --from=frontend /app/frontend/dist /srv
COPY --from=extension /memorylane-extension.zip /srv/memorylane-extension.zip
COPY --from=models /models /srv/models
