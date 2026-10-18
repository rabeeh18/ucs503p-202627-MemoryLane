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

FROM caddy:2
COPY deploy/caddy/Caddyfile /etc/caddy/Caddyfile
COPY --from=frontend /app/frontend/dist /srv
