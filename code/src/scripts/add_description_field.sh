#!/usr/bin/env bash
# Adds the stored `description` field to an existing schema-v2 core via the
# Schema API, without touching anything else. Safe to run more than once.
#
# Run this BEFORE deploying a backend that writes `description`: the core has
# schemaless field creation turned off, so saves would fail without the field.
#
# Usage: CORE_NAME=memorylane_v2 bash scripts/add_description_field.sh
set -e

SOLR_HOST=${SOLR_HOST:-localhost}
SOLR_PORT=${SOLR_PORT:-8983}
CORE_NAME=${CORE_NAME:-memorylane_v2}
SCHEMA_URL="http://${SOLR_HOST}:${SOLR_PORT}/solr/${CORE_NAME}/schema"
FIELD='{"name":"description","type":"string","indexed":false,"stored":true,"docValues":false}'

curl -sf "${SCHEMA_URL}/fields/description" > /dev/null 2>&1 && {
  echo "[INFO] Field 'description' already exists in ${CORE_NAME}; updating its definition."
  curl -sf -X POST "$SCHEMA_URL" -H 'Content-Type: application/json' -d "{\"replace-field\": $FIELD}" > /dev/null
  echo "[INFO] Done."
  exit 0
}

curl -sf -X POST "$SCHEMA_URL" -H 'Content-Type: application/json' -d "{\"add-field\": $FIELD}" > /dev/null \
  || { echo "[ERROR] Could not add 'description' to ${CORE_NAME} at ${SCHEMA_URL}"; exit 1; }
curl -sf "${SCHEMA_URL}/fields/description" > /dev/null \
  || { echo "[ERROR] 'description' was not added"; exit 1; }
echo "[INFO] Added field 'description' to ${CORE_NAME}."
