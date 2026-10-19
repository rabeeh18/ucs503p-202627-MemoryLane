#!/usr/bin/env bash
# Adds the `page_embedding` field (one vector per page, on chunk 0) to an existing
# schema-v2 core via the Schema API, without touching anything else. Safe to re-run.
#
# Run this BEFORE deploying a backend that writes `page_embedding`: the core has
# schemaless field creation turned off, so saves would fail without the field.
#
# Usage: CORE_NAME=memorylane_v2 bash scripts/add_page_embedding_field.sh
set -e

SOLR_HOST=${SOLR_HOST:-localhost}
SOLR_PORT=${SOLR_PORT:-8983}
CORE_NAME=${CORE_NAME:-memorylane_v2}
SCHEMA_URL="http://${SOLR_HOST}:${SOLR_PORT}/solr/${CORE_NAME}/schema"
FIELD='{"name":"page_embedding","type":"knn_vector_384","indexed":true,"stored":true}'

curl -sf "${SCHEMA_URL}/fields/page_embedding" > /dev/null 2>&1 && {
  echo "[INFO] Field 'page_embedding' already exists in ${CORE_NAME}; updating its definition."
  curl -sf -X POST "$SCHEMA_URL" -H 'Content-Type: application/json' -d "{\"replace-field\": $FIELD}" > /dev/null
  echo "[INFO] Done."
  exit 0
}

curl -sf -X POST "$SCHEMA_URL" -H 'Content-Type: application/json' -d "{\"add-field\": $FIELD}" > /dev/null \
  || { echo "[ERROR] Could not add 'page_embedding' to ${CORE_NAME} at ${SCHEMA_URL}"; exit 1; }
curl -sf "${SCHEMA_URL}/fields/page_embedding" > /dev/null \
  || { echo "[ERROR] 'page_embedding' was not added"; exit 1; }
echo "[INFO] Added field 'page_embedding' to ${CORE_NAME}."
