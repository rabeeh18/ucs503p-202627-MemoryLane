# API Reference

MemoryLane exposes a small FastAPI interface for health checks, memory ingestion, search, and optional summarization.

## Endpoints

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Check backend dependencies |
| `POST` | `/memory` | Store a webpage memory |
| `POST` | `/search` | Search stored memories |
| `POST` | `/summarize` | Summarize a selected memory |

The API models are defined in `backend/models.py`.

See [API Endpoints](endpoints.md) for request and response details.
