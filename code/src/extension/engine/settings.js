// Search settings, the same numbers the server uses (backend/config.py). The
// extension refreshes them from GET /api/search-settings when it can, so a
// value changed on the server (.env) applies to local search too; these are
// the defaults until then. tests/test_extension_settings.py keeps them equal
// to the server's defaults.
export const DEFAULT_SETTINGS = Object.freeze({
    DEFAULT_TOP_K: 5,
    DEFAULT_CANDIDATE_POOL: 50,
    RRF_K: 60,
    BM25_WEIGHT: 1.0,
    VECTOR_WEIGHT: 1.0,
    PAGE_SECOND_CHUNK_WEIGHT: 0.0,
    MIN_VECTOR_SIMILARITY: 0.55,
    KEYWORD_FULL_MATCH: 0.75,
    QUERY_INTENT_ENABLED: true,
    INTENT_WEIGHT: 1.0,
    CHUNK_MAX_WORDS: 150,
    CHUNK_MIN_WORDS: 40,
    CHUNK_OVERLAP_WORDS: 30,
    MAX_PAGES_PER_USER: 5000,
    EMBEDDING_MODEL: "BAAI/bge-small-en-v1.5",
    EMBEDDING_DIM: 384,
    EMBEDDING_QUERY_PREFIX: "Represent this sentence for searching relevant passages: ",
});

// Live values: a mutable copy the engine reads (applySettings updates it).
export const SETTINGS = { ...DEFAULT_SETTINGS };

/** Take the server's values for the keys this engine knows. */
export function applySettings(values) {
    for (const key of Object.keys(DEFAULT_SETTINGS)) {
        if (values && typeof values[key] === typeof DEFAULT_SETTINGS[key]) SETTINGS[key] = values[key];
    }
}
