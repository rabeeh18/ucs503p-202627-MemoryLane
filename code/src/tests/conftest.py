import os

# Test-only Cognito settings, set before backend.config is imported. Real values
# from .env don't apply because load_dotenv never overrides existing variables.
os.environ["COGNITO_REGION"] = "ap-south-1"
os.environ["COGNITO_USER_POOL_ID"] = "ap-south-1_TESTPOOL"
os.environ["COGNITO_APP_CLIENT_ID"] = "test-client-id"
# Sign-in linking is off unless a test turns it on; its database never touches data/.
os.environ["COGNITO_DOMAIN"] = ""
os.environ["VITE_COGNITO_DOMAIN"] = ""
os.environ["ACCOUNTS_DB"] = ":memory:"
# No real Gemini calls from tests: tests that need it patch it in.
os.environ["GEMINI_API_KEY"] = ""


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _no_real_sentence_embeddings(monkeypatch):
    """Search builds snippets with sentence embeddings; never load the model in tests."""
    from backend import retrieval

    def fake_embed_passages(texts):
        return [[float(len(t) % 7), 1.0, 0.0] for t in texts]

    monkeypatch.setattr(retrieval, "embed_passages", fake_embed_passages)
    monkeypatch.setattr(retrieval, "_sentence_embeddings",
                        retrieval.SentenceEmbeddingCache(lambda texts: retrieval.embed_passages(texts)))
