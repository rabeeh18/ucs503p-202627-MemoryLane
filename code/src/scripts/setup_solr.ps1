# Creates (or updates) the MemoryLane Solr core with schema v2.
# Mirrors scripts/setup_solr.sh, which is the single source of truth for the schema.
#
# Usage: $env:CORE_NAME = "memorylane_v2"; .\scripts\setup_solr.ps1 [-Reset]
param(
    [switch]$Reset
)

$ErrorActionPreference = "Stop"

$SOLR_HOST = if ($env:SOLR_HOST) { $env:SOLR_HOST } else { "localhost" }
$SOLR_PORT = if ($env:SOLR_PORT) { $env:SOLR_PORT } else { 8983 }
$SOLR_BASE = "http://${SOLR_HOST}:${SOLR_PORT}/solr"
$CORE_NAME = if ($env:CORE_NAME) { $env:CORE_NAME } else { "memorylane_v2" }

function Write-Info($msg) { Write-Host "[INFO] $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "[WARN] $msg" -ForegroundColor Yellow }
function Write-ErrorMsg($msg) { Write-Host "[ERROR] $msg" -ForegroundColor Red; exit 1 }

$headers = @{ "Content-Type" = "application/json" }

function Invoke-Schema($body) {
    Invoke-RestMethod -Method Post -Uri "${SOLR_BASE}/${CORE_NAME}/schema" -Headers $headers -Body ($body | ConvertTo-Json -Depth 10) | Out-Null
}

# Step 1: Check Solr
Write-Info "Checking if Solr is running..."
try {
    Invoke-RestMethod -Uri "${SOLR_BASE}/admin/cores?action=STATUS" -ErrorAction Stop | Out-Null
    Write-Info "Solr is running."
} catch {
    Write-ErrorMsg "Solr is not reachable at ${SOLR_BASE}"
}

# Step 1b: Require Solr 9.x (DenseVectorField, knn pre-filtering)
Write-Info "Checking Solr version..."
try {
    $sysInfo = Invoke-RestMethod -Uri "${SOLR_BASE}/admin/info/system?wt=json"
    $solrVersion = $sysInfo.lucene.'solr-spec-version'
    $major = [int]($solrVersion.Split('.')[0])
    if ($major -lt 9) {
        Write-ErrorMsg "Solr 9.x is required for DenseVectorField (detected: $solrVersion)."
    }
    Write-Info "Solr version $solrVersion is compatible."
} catch {
    Write-Warn "Could not verify Solr version; continuing. DenseVectorField requires Solr 9+."
}

# Step 2: Check core existence
$coresStatus = Invoke-RestMethod -Uri "${SOLR_BASE}/admin/cores?action=STATUS&core=${CORE_NAME}"
$coreExists = $null -ne $coresStatus.status.$CORE_NAME.name

# Step 3: Reset if requested
if ($Reset -and $coreExists) {
    Write-Warn "Resetting core '${CORE_NAME}'..."
    Invoke-RestMethod -Uri "${SOLR_BASE}/admin/cores?action=UNLOAD&core=${CORE_NAME}&deleteInstanceDir=true" | Out-Null
    $coreExists = $false
    Write-Info "Core unloaded."
}

# Step 4: Create core if needed
if (-not $coreExists) {
    Write-Info "Creating core '${CORE_NAME}'..."
    try {
        Invoke-RestMethod -Uri "${SOLR_BASE}/admin/cores?action=CREATE&name=${CORE_NAME}&configSet=_default" | Out-Null
        Write-Info "Core created."
    } catch {
        Write-ErrorMsg "Failed to create core: $_"
    }
} else {
    Write-Info "Core '${CORE_NAME}' already exists."
}

# Step 5: Turn off schemaless field guessing so only the fields below exist
try {
    $cfg = @{ "set-user-property" = @{ "update.autoCreateFields" = "false" } }
    Invoke-RestMethod -Method Post -Uri "${SOLR_BASE}/${CORE_NAME}/config" -Headers $headers -Body ($cfg | ConvertTo-Json -Depth 10) | Out-Null
} catch {
    Write-Warn "Could not disable autoCreateFields"
}

# Step 6: Install schema via Schema API
Write-Info "Installing schema..."

$knnFieldType = @{
    "name" = "knn_vector_384"
    "class" = "solr.DenseVectorField"
    "vectorDimension" = 384
    "vectorEncoding" = "FLOAT32"
    "similarityFunction" = "cosine"
}

try {
    Invoke-Schema @{ "replace-field-type" = $knnFieldType }
} catch {
    try {
        Invoke-Schema @{ "add-field-type" = $knnFieldType }
    } catch {
        Write-Warn "Field type knn_vector_384 may already exist"
    }
}

# title/text use text_en from _default: possessive filter, stopwords, Porter stemming.
# 'id' (string) exists by default and holds {page_id}::{chunk_index}.
$fields = @(
    @{ name="user_id"; type="string"; indexed=$true; stored=$true; docValues=$true },
    @{ name="page_id"; type="string"; indexed=$true; stored=$true; docValues=$true },
    @{ name="url"; type="string"; indexed=$true; stored=$true },
    @{ name="title"; type="text_en"; indexed=$true; stored=$true },
    @{ name="domain"; type="string"; indexed=$true; stored=$true },
    @{ name="text"; type="text_en"; indexed=$true; stored=$true },
    @{ name="chunk_id"; type="pint"; indexed=$true; stored=$true },
    @{ name="total_chunks"; type="pint"; indexed=$true; stored=$true },
    @{ name="timestamp"; type="pdate"; indexed=$true; stored=$true; docValues=$true },
    @{ name="content_hash"; type="string"; indexed=$true; stored=$true },
    @{ name="embedding_model"; type="string"; indexed=$true; stored=$true },
    @{ name="description"; type="string"; indexed=$false; stored=$true; docValues=$false },
    @{ name="embedding"; type="knn_vector_384"; indexed=$true; stored=$false }
)

foreach ($field in $fields) {
    try {
        Invoke-Schema @{ "replace-field" = $field }
    } catch {
        try {
            Invoke-Schema @{ "add-field" = $field }
        } catch {
            Write-ErrorMsg "Could not install field: $($field.name)"
        }
    }
}

Write-Info "Schema fields installed."

# Step 7: Reload core
Write-Info "Reloading core..."
try {
    Invoke-RestMethod -Uri "${SOLR_BASE}/admin/cores?action=RELOAD&core=${CORE_NAME}" | Out-Null
    Write-Info "Core reloaded."
} catch {
    Write-ErrorMsg "Failed to reload core"
}

# Step 8: Verify ping
Write-Info "Verifying core..."
try {
    Invoke-RestMethod -Uri "${SOLR_BASE}/${CORE_NAME}/admin/ping" | Out-Null
    Write-Info "Core is healthy."
} catch {
    Write-ErrorMsg "Core ping failed"
}

# Step 9: Smoke test: index, BM25 (with stemming), KNN with a user_id filter, delete
Write-Info "Testing document indexing..."
$vector = @()
for ($i=0; $i -lt 384; $i++) { $vector += 0.1 }

$testDoc = @{
    id = "test_setup_doc::0"
    user_id = "setup_test_user"
    page_id = "test_setup_doc"
    url = "https://test.com/"
    title = "Test Document"
    domain = "test.com"
    text = "This document is about learning setup verification"
    chunk_id = 0
    total_chunks = 1
    timestamp = "2024-01-01T00:00:00Z"
    content_hash = "test"
    embedding_model = "test"
    description = "A test page."
    embedding = $vector
}

try {
    # Solr JSON update treats top-level object keys as commands (add/delete/commit).
    # PowerShell ConvertTo-Json also unwraps a single-item array into an object, so
    # posting @{url=...} makes Solr report: Unknown command 'url'.
    $indexBody = ConvertTo-Json -InputObject @{ add = @{ doc = $testDoc } } -Depth 10 -Compress
    Invoke-RestMethod -Method Post -Uri "${SOLR_BASE}/${CORE_NAME}/update?commit=true" -Headers $headers -Body $indexBody | Out-Null
    Write-Info "Test document indexed."
} catch {
    Write-ErrorMsg "Failed to index test document: $_"
}

Write-Info "Testing BM25 search..."
$userFilter = [uri]::EscapeDataString("{!term f=user_id}setup_test_user")
$bm25Result = Invoke-RestMethod -Uri "${SOLR_BASE}/${CORE_NAME}/select?q=learn&df=text&fq=${userFilter}&fl=id&rows=1"
if ($bm25Result.response.numFound -gt 0) {
    Write-Info "BM25 search works (stemming: 'learn' matched 'learning')."
} else {
    Write-ErrorMsg "BM25 search failed (is stemming active?)"
}

Write-Info "Testing KNN search with user filter..."
$knnQuery = @{
    query = "{!knn f=embedding topK=1}[$($vector -join ',')]"
    filter = "{!term f=user_id}setup_test_user"
    fields = "id,score"
    limit = 1
}
try {
    $knnResult = Invoke-RestMethod -Method Post -Uri "${SOLR_BASE}/${CORE_NAME}/select" -Headers $headers -Body ($knnQuery | ConvertTo-Json -Depth 10)
    if ($knnResult.response.numFound -gt 0) {
        Write-Info "KNN vector search works."
    } else {
        Write-ErrorMsg "KNN search failed"
    }
} catch {
    Write-ErrorMsg "KNN search failed: $_"
}

Write-Info "Cleaning up test document..."
try {
    $deleteReq = @{ delete = @{ query = "page_id:test_setup_doc" } }
    Invoke-RestMethod -Method Post -Uri "${SOLR_BASE}/${CORE_NAME}/update?commit=true" -Headers $headers -Body ($deleteReq | ConvertTo-Json -Depth 10) | Out-Null
    Write-Info "Test document cleaned up."
} catch {
    Write-Warn "Failed to clean up test document"
}

Write-Host ""
Write-Info "========================================"
Write-Info "MemoryLane Solr setup complete!"
Write-Info "Core: ${CORE_NAME}"
Write-Info "URL: ${SOLR_BASE}/${CORE_NAME}"
Write-Info "========================================"
