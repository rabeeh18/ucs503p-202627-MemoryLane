import json
import chromadb

DB_PATH = "./chroma_db"
OUTPUT_FILE = "chroma_export.json"

# Connect to existing ChromaDB
client = chromadb.PersistentClient(path=DB_PATH)

# Find the collection automatically
collections = client.list_collections()

if not collections:
    print("No ChromaDB collections found.")
    raise SystemExit(1)

print("Collections found:")
for c in collections:
    print(f"- {c.name}")

# Use the first collection
collection = client.get_collection(collections[0].name)

print(f"\nUsing collection: {collection.name}")

# Get stored chunks + metadata
data = collection.get(
    include=["documents", "metadatas"]
)

records = {}

for doc, metadata in zip(
    data["documents"],
    data["metadatas"]
):
    metadata = metadata or {}

    url = metadata.get("url", "")

    if not url:
        continue

    # Create one webpage entry per URL
    if url not in records:
        records[url] = {
            "url": url,
            "title": metadata.get("title", ""),
            "chunks": []
        }

    # Add this chunk to the webpage
    if doc and doc.strip():
        records[url]["chunks"].append(doc)

# Convert dictionary → list
export = list(records.values())

# Save JSON
with open(
    OUTPUT_FILE,
    "w",
    encoding="utf-8"
) as f:
    json.dump(
        export,
        f,
        ensure_ascii=False,
        indent=2
    )

print(f"\nExported {len(export)} unique webpages")
print(f"Saved to: {OUTPUT_FILE}")