param(
    [switch]$Reset
)

$ErrorActionPreference = "Stop"

$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$PROJECT_ROOT = Split-Path -Parent $SCRIPT_DIR

$SOLR_HOST = if ($env:SOLR_HOST) { $env:SOLR_HOST } else { "localhost" }
$SOLR_PORT = if ($env:SOLR_PORT) { $env:SOLR_PORT } else { 8983 }
$SOLR_BASE = "http://${SOLR_HOST}:${SOLR_PORT}/solr"
$CORE_NAME = "memorylane"

function Write-Info($msg) { Write-Host "[INFO] $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "[WARN] $msg" -ForegroundColor Yellow }
function Write-ErrorMsg($msg) { Write-Host "[ERROR] $msg" -ForegroundColor Red; exit 1 }

# Step 1: Check Solr
Write-Info "Checking if Solr is running..."
try {
    Invoke-RestMethod -Uri "${SOLR_BASE}/admin/cores?action=STATUS" -ErrorAction Stop | Out-Null
    Write-Info "Solr is running."
} catch {
    Write-ErrorMsg "Solr is not reachable at ${SOLR_BASE}"
}

# Step 1b: Require Solr 9.x (DenseVectorField)
Write-Info "Checking Solr version..."
try {
    $sysInfo = Invoke-RestMethod -Uri "http://${SOLR_HOST}:${SOLR_PORT}/solr/admin/info/system?wt=json"
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
        $response = Invoke-RestMethod -Uri "${SOLR_BASE}/admin/cores?action=CREATE&name=${CORE_NAME}&configSet=_default"
        Write-Info "Core created."
    } catch {
        Write-ErrorMsg "Failed to create core: $_"
    }
} else {
    Write-Info "Core '${CORE_NAME}' already exists."
}

# Step 5: Install schema via Schema API
Write-Info "Installing schema..."

$headers = @{ "Content-Type" = "application/json" }

# Add field types
$knnFieldType = @{
    "name" = "knn_vector_384"
    "class" = "solr.DenseVectorField"
    "vectorDimension" = 384
    "vectorEncoding" = "FLOAT32"
    "similarityFunction" = "cosine"
}

try {
    Invoke-RestMethod -Method Post -Uri "${SOLR_BASE}/${CORE_NAME}/schema" -Headers $headers -Body (@{ "replace-field-type" = $knnFieldType } | ConvertTo-Json -Depth 10) | Out-Null
} catch {
    try {
        Invoke-RestMethod -Method Post -Uri "${SOLR_BASE}/${CORE_NAME}/schema" -Headers $headers -Body (@{ "add-field-type" = $knnFieldType } | ConvertTo-Json -Depth 10) | Out-Null
    } catch {
        Write-Warn "Field type knn_vector_384 may already exist"
    }
}

$fields = @(
    @{ name="webpage_id"; type="string"; indexed=$true; stored=$true },
    @{ name="url"; type="string"; indexed=$true; stored=$true },
    @{ name="title"; type="text_general"; indexed=$true; stored=$true },
    @{ name="domain"; type="string"; indexed=$true; stored=$true },
    @{ name="text"; type="text_general"; indexed=$true; stored=$true },
    @{ name="chunk_id"; type="pint"; indexed=$true; stored=$true },
    @{ name="total_chunks"; type="pint"; indexed=$true; stored=$true },
    @{ name="timestamp"; type="string"; indexed=$true; stored=$true; docValues=$true },
    @{ name="embedding"; type="knn_vector_384"; indexed=$true; stored=$true }
)

foreach ($field in $fields) {
    try {
        Invoke-RestMethod -Method Post -Uri "${SOLR_BASE}/${CORE_NAME}/schema" -Headers $headers -Body (@{ "replace-field" = $field } | ConvertTo-Json -Depth 10) | Out-Null
    } catch {
        try {
            Invoke-RestMethod -Method Post -Uri "${SOLR_BASE}/${CORE_NAME}/schema" -Headers $headers -Body (@{ "add-field" = $field } | ConvertTo-Json -Depth 10) | Out-Null
        } catch {
            Write-Warn "Field may already exist: $($field.name)"
        }
    }
}

Write-Info "Schema fields installed."

# Step 6: Reload core
Write-Info "Reloading core..."
try {
    Invoke-RestMethod -Uri "${SOLR_BASE}/admin/cores?action=RELOAD&core=${CORE_NAME}" | Out-Null
    Write-Info "Core reloaded."
} catch {
    Write-ErrorMsg "Failed to reload core"
}

# Step 7: Verify ping
Write-Info "Verifying core..."
try {
    Invoke-RestMethod -Uri "${SOLR_BASE}/${CORE_NAME}/admin/ping" | Out-Null
    Write-Info "Core is healthy."
} catch {
    Write-ErrorMsg "Core ping failed"
}

# Step 8: Test document indexing with vector
Write-Info "Testing document indexing..."
$vector = @()
for ($i=0; $i -lt 384; $i++) { $vector += 0.1 }

$testDoc = @{
    id = "test_setup_doc"
    webpage_id = "test"
    url = "https://test.com"
    title = "Test Document"
    domain = "test.com"
    text = "This is a test document for setup verification"
    chunk_id = 0
    total_chunks = 1
    timestamp = "2024-01-01T00:00:00Z"
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

# Step 9: Test BM25 search
Write-Info "Testing BM25 search..."
$bm25Result = Invoke-RestMethod -Uri "${SOLR_BASE}/${CORE_NAME}/select?q=test+document&df=text&fl=id&rows=1"
if ($bm25Result.response.numFound -gt 0) {
    Write-Info "BM25 search works."
} else {
    Write-ErrorMsg "BM25 search failed"
}

# Step 10: Test KNN search
Write-Info "Testing KNN search..."
$knnQuery = @{
    query = "{!knn f=embedding topK=1}[$($vector -join ',')]"
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

# Step 11: Clean up test document
Write-Info "Cleaning up test document..."
try {
    $deleteReq = @{ delete = @{ query = "id:test_setup_doc" } }
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
