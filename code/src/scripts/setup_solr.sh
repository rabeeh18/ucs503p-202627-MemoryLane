#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

SOLR_HOST=${SOLR_HOST:-localhost}
SOLR_PORT=${SOLR_PORT:-8983}
SOLR_BASE="http://${SOLR_HOST}:${SOLR_PORT}/solr"
CORE_NAME="memorylane"
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

# Step 1: Check Solr
info "Checking if Solr is running..."
curl -sf "${SOLR_BASE}/admin/cores?action=STATUS" > /dev/null || error "Solr is not reachable at ${SOLR_BASE}"
info "Solr is running."

# Step 1b: Require Solr 9.x (DenseVectorField)
info "Checking Solr version..."
SOLR_VERSION=$(curl -sf "http://${SOLR_HOST}:${SOLR_PORT}/solr/admin/info/system?wt=json" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('lucene',{}).get('solr-spec-version','0'))" 2>/dev/null || echo "0")
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

# Step 5: Install schema via Schema API
info "Installing schema..."

# Add field types
curl -sf -X POST "${SOLR_BASE}/${CORE_NAME}/schema" -H 'Content-Type: application/json' -d '{
  "replace-field-type": {
    "name": "knn_vector_384",
    "class": "solr.DenseVectorField",
    "vectorDimension": 384,
    "vectorEncoding": "FLOAT32",
    "similarityFunction": "cosine"
  }
}' > /dev/null 2>&1 || 
curl -sf -X POST "${SOLR_BASE}/${CORE_NAME}/schema" -H 'Content-Type: application/json' -d '{
  "add-field-type": {
    "name": "knn_vector_384",
    "class": "solr.DenseVectorField",
    "vectorDimension": 384,
    "vectorEncoding": "FLOAT32",
    "similarityFunction": "cosine"
  }
}' > /dev/null 2>&1 || warn "Field type knn_vector_384 may already exist"

# Add/replace fields (skip 'id' since it exists by default)
for FIELD_JSON in \
  '{"name":"webpage_id","type":"string","indexed":true,"stored":true}' \
  '{"name":"url","type":"string","indexed":true,"stored":true}' \
  '{"name":"title","type":"text_general","indexed":true,"stored":true}' \
  '{"name":"domain","type":"string","indexed":true,"stored":true}' \
  '{"name":"text","type":"text_general","indexed":true,"stored":true}' \
  '{"name":"chunk_id","type":"pint","indexed":true,"stored":true}' \
  '{"name":"total_chunks","type":"pint","indexed":true,"stored":true}' \
  '{"name":"timestamp","type":"string","indexed":true,"stored":true,"docValues":true}' \
  '{"name":"embedding","type":"knn_vector_384","indexed":true,"stored":true}'; do
  
  # Try replace first, then add
  curl -sf -X POST "${SOLR_BASE}/${CORE_NAME}/schema" -H 'Content-Type: application/json' \
    -d "{\"replace-field\": $FIELD_JSON}" > /dev/null 2>&1 || \
  curl -sf -X POST "${SOLR_BASE}/${CORE_NAME}/schema" -H 'Content-Type: application/json' \
    -d "{\"add-field\": $FIELD_JSON}" > /dev/null 2>&1 || \
  warn "Field may already exist: $(echo $FIELD_JSON | python3 -c 'import sys,json;print(json.load(sys.stdin)["name"])')"
done

info "Schema fields installed."

# Step 6: Reload core
info "Reloading core..."
curl -sf "${SOLR_BASE}/admin/cores?action=RELOAD&core=${CORE_NAME}" > /dev/null || error "Failed to reload core"
info "Core reloaded."

# Step 7: Verify ping
info "Verifying core..."
curl -sf "${SOLR_BASE}/${CORE_NAME}/admin/ping" > /dev/null || error "Core ping failed"
info "Core is healthy."

# Step 8: Test document indexing with vector
info "Testing document indexing..."
TEST_VECTOR=$(python3 -c "print('[' + ','.join(['0.1'] * 384) + ']')")
curl -sf -X POST "${SOLR_BASE}/${CORE_NAME}/update?commit=true" -H 'Content-Type: application/json' -d "[
  {\"id\": \"test_setup_doc\", \"webpage_id\": \"test\", \"url\": \"https://test.com\", \"title\": \"Test Document\", \"domain\": \"test.com\", \"text\": \"This is a test document for setup verification\", \"chunk_id\": 0, \"total_chunks\": 1, \"timestamp\": \"2024-01-01T00:00:00Z\", \"embedding\": $TEST_VECTOR}
]" > /dev/null || error "Failed to index test document"
info "Test document indexed."

# Step 9: Test BM25 search
info "Testing BM25 search..."
BM25_RESULT=$(curl -sf "${SOLR_BASE}/${CORE_NAME}/select?q=test+document&df=text&fl=id&rows=1")
echo "$BM25_RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['response']['numFound'] > 0" || error "BM25 search failed"
info "BM25 search works."

# Step 10: Test KNN search  
info "Testing KNN search..."
KNN_RESULT=$(curl -sf -X POST "${SOLR_BASE}/${CORE_NAME}/select" -H 'Content-Type: application/json' -d "{
  \"query\": \"{!knn f=embedding topK=1}$TEST_VECTOR\",
  \"fields\": \"id,score\",
  \"limit\": 1
}")
echo "$KNN_RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['response']['numFound'] > 0" || error "KNN search failed"
info "KNN vector search works."

# Step 11: Clean up test document
info "Cleaning up test document..."
curl -sf -X POST "${SOLR_BASE}/${CORE_NAME}/update?commit=true" -H 'Content-Type: application/json' -d '{"delete": {"query": "id:test_setup_doc"}}' > /dev/null
info "Test document cleaned up."

echo ""
info "========================================"
info "MemoryLane Solr setup complete!"
info "Core: ${CORE_NAME}"
info "URL: ${SOLR_BASE}/${CORE_NAME}"
info "========================================"
