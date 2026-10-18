#!/usr/bin/env bash
# Creates (or updates) the MemoryLane Solr core with schema v2.
# This script is the single source of truth for the schema; setup_solr.ps1 mirrors it.
#
# Usage: CORE_NAME=memorylane_v2 ./scripts/setup_solr.sh [--reset]
set -e

SOLR_HOST=${SOLR_HOST:-localhost}
SOLR_PORT=${SOLR_PORT:-8983}
SOLR_BASE="http://${SOLR_HOST}:${SOLR_PORT}/solr"
CORE_NAME=${CORE_NAME:-memorylane_v2}
RESET=false

# Parse args
for arg in "$@"; do
    case $arg in
        --reset) RESET=true ;;
    esac
done

# Color output helpers
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

info() { echo -e "${GREEN}[INFO]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

schema_post() {
  curl -sf -X POST "${SOLR_BASE}/${CORE_NAME}/schema" -H 'Content-Type: application/json' -d "$1" > /dev/null 2>&1
}

# Step 1: Check Solr
info "Checking if Solr is running..."
curl -sf "${SOLR_BASE}/admin/cores?action=STATUS" > /dev/null || error "Solr is not reachable at ${SOLR_BASE}"
info "Solr is running."

# Step 1b: Require Solr 9.x (DenseVectorField, knn pre-filtering)
info "Checking Solr version..."
SOLR_VERSION=$(curl -sf "${SOLR_BASE}/admin/info/system?wt=json" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('lucene',{}).get('solr-spec-version','0'))" 2>/dev/null || echo "0")
MAJOR=$(echo "$SOLR_VERSION" | cut -d. -f1)
if [ "$MAJOR" -lt 9 ] 2>/dev/null; then
    error "Solr 9.x is required for DenseVectorField (detected: ${SOLR_VERSION})."
fi
info "Solr version ${SOLR_VERSION} is compatible."

# Step 2: Check core existence
CORE_EXISTS=$(curl -sf "${SOLR_BASE}/admin/cores?action=STATUS&core=${CORE_NAME}" | python3 -c "import sys,json; d=json.load(sys.stdin); print('true' if d.get('status',{}).get('${CORE_NAME}',{}).get('name') else 'false')")

# Step 3: Reset if requested
if [ "$RESET" = true ] && [ "$CORE_EXISTS" = "true" ]; then
    warn "Resetting core '${CORE_NAME}'..."
    curl -sf "${SOLR_BASE}/admin/cores?action=UNLOAD&core=${CORE_NAME}&deleteInstanceDir=true" > /dev/null
    CORE_EXISTS=false
    info "Core unloaded."
fi

# Step 4: Create core if needed
if [ "$CORE_EXISTS" = "false" ]; then
    info "Creating core '${CORE_NAME}'..."
    RESPONSE=$(curl -sf "${SOLR_BASE}/admin/cores?action=CREATE&name=${CORE_NAME}&configSet=_default")
    echo "$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); sys.exit(0 if 'error' not in d else 1)" || error "Failed to create core: $RESPONSE"
    info "Core created."
else
    info "Core '${CORE_NAME}' already exists."
fi

# Step 5: Turn off schemaless field guessing so only the fields below exist
curl -sf -X POST "${SOLR_BASE}/${CORE_NAME}/config" -H 'Content-Type: application/json' \
  -d '{"set-user-property": {"update.autoCreateFields": "false"}}' > /dev/null || warn "Could not disable autoCreateFields"

# Step 6: Install schema via Schema API
info "Installing schema..."

KNN_TYPE='{"name":"knn_vector_384","class":"solr.DenseVectorField","vectorDimension":384,"vectorEncoding":"FLOAT32","similarityFunction":"cosine"}'
schema_post "{\"replace-field-type\": $KNN_TYPE}" || \
schema_post "{\"add-field-type\": $KNN_TYPE}" || \
warn "Field type knn_vector_384 may already exist"

# title/text use text_en from _default: possessive filter, stopwords, Porter stemming.
# 'id' (string) exists by default and holds {page_id}::{chunk_index}.
for FIELD_JSON in \
  '{"name":"user_id","type":"string","indexed":true,"stored":true,"docValues":true}' \
  '{"name":"page_id","type":"string","indexed":true,"stored":true,"docValues":true}' \
  '{"name":"url","type":"string","indexed":true,"stored":true}' \
  '{"name":"title","type":"text_en","indexed":true,"stored":true}' \
  '{"name":"domain","type":"string","indexed":true,"stored":true}' \
  '{"name":"text","type":"text_en","indexed":true,"stored":true}' \
  '{"name":"chunk_id","type":"pint","indexed":true,"stored":true}' \
  '{"name":"total_chunks","type":"pint","indexed":true,"stored":true}' \
  '{"name":"timestamp","type":"pdate","indexed":true,"stored":true,"docValues":true}' \
  '{"name":"content_hash","type":"string","indexed":true,"stored":true}' \
  '{"name":"embedding_model","type":"string","indexed":true,"stored":true}' \
  '{"name":"embedding","type":"knn_vector_384","indexed":true,"stored":false}'; do

  # Try replace first, then add
  schema_post "{\"replace-field\": $FIELD_JSON}" || \
  schema_post "{\"add-field\": $FIELD_JSON}" || \
  error "Could not install field: $(echo $FIELD_JSON | python3 -c 'import sys,json;print(json.load(sys.stdin)["name"])')"
done

info "Schema fields installed."

# Step 7: Reload core
info "Reloading core..."
curl -sf "${SOLR_BASE}/admin/cores?action=RELOAD&core=${CORE_NAME}" > /dev/null || error "Failed to reload core"
info "Core reloaded."

# Step 8: Verify ping
info "Verifying core..."
curl -sf "${SOLR_BASE}/${CORE_NAME}/admin/ping" > /dev/null || error "Core ping failed"
info "Core is healthy."

# Step 9: Smoke test: index, BM25 (with stemming), KNN with a user_id filter, delete
info "Testing document indexing..."
TEST_VECTOR=$(python3 -c "print('[' + ','.join(['0.1'] * 384) + ']')")
curl -sf -X POST "${SOLR_BASE}/${CORE_NAME}/update?commit=true" -H 'Content-Type: application/json' -d "[
  {\"id\": \"test_setup_doc::0\", \"user_id\": \"setup_test_user\", \"page_id\": \"test_setup_doc\", \"url\": \"https://test.com/\", \"title\": \"Test Document\", \"domain\": \"test.com\", \"text\": \"This document is about learning setup verification\", \"chunk_id\": 0, \"total_chunks\": 1, \"timestamp\": \"2024-01-01T00:00:00Z\", \"content_hash\": \"test\", \"embedding_model\": \"test\", \"embedding\": $TEST_VECTOR}
]" > /dev/null || error "Failed to index test document"
info "Test document indexed."

info "Testing BM25 search..."
BM25_RESULT=$(curl -sf -G "${SOLR_BASE}/${CORE_NAME}/select" --data-urlencode "q=learn" --data-urlencode "df=text" \
  --data-urlencode "fq={!term f=user_id}setup_test_user" --data-urlencode "fl=id" --data-urlencode "rows=1")
echo "$BM25_RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['response']['numFound'] > 0" || error "BM25 search failed (is stemming active?)"
info "BM25 search works (stemming: 'learn' matched 'learning')."

info "Testing KNN search with user filter..."
KNN_RESULT=$(curl -sf -X POST "${SOLR_BASE}/${CORE_NAME}/select" -H 'Content-Type: application/json' -d "{
  \"query\": \"{!knn f=embedding topK=1}$TEST_VECTOR\",
  \"filter\": \"{!term f=user_id}setup_test_user\",
  \"fields\": \"id,score\",
  \"limit\": 1
}")
echo "$KNN_RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['response']['numFound'] > 0" || error "KNN search failed"
info "KNN vector search works."

info "Cleaning up test document..."
curl -sf -X POST "${SOLR_BASE}/${CORE_NAME}/update?commit=true" -H 'Content-Type: application/json' -d '{"delete": {"query": "page_id:test_setup_doc"}}' > /dev/null
info "Test document cleaned up."

echo ""
info "========================================"
info "MemoryLane Solr setup complete!"
info "Core: ${CORE_NAME}"
info "URL: ${SOLR_BASE}/${CORE_NAME}"
info "========================================"
