import argparse
import sys
import logging
from backend.retrieval import hybrid_search
from backend.summarizer import summarize, detect_detail_level, is_gemini_available
from backend.solr_client import get_solr_client
from backend.embeddings import get_model


def main():
    parser = argparse.ArgumentParser(description="MemoryLane CLI - Search your browsing memories")
    parser.add_argument("query", help="Search query")
    parser.add_argument("--top-k", type=int, default=5, help="Number of results (default: 5)")
    parser.add_argument("--candidates", type=int, default=30, help="Candidate pool size (default: 30)")
    parser.add_argument("--debug", action="store_true", help="Show debug scores")
    parser.add_argument("--no-summarize", action="store_true", help="Disable Gemini summarization")
    
    args = parser.parse_args()
    
    # Setup logging
    logging.basicConfig(level=logging.WARNING)
    
    # Pre-load model
    print("Loading embedding model...")
    get_model()
    
    # Run search
    print(f"\nSearching for: \"{args.query}\"\n")
    
    try:
        results = hybrid_search(args.query, top_k=args.top_k, candidate_pool=args.candidates)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
    
    if not results:
        print("No results found.")
        return
    
    print("=" * 50)
    print("MEMORYLANE SEARCH RESULTS")
    print("=" * 50)
    print(f"\nQuery: \"{args.query}\"")
    print(f"Results: {len(results)}\n")
    
    for result in results:
        print(f"{result['rank']}. {result.get('title', 'Untitled')}")
        print(f"   {result.get('url', '')}")
        print(f"   {result.get('timestamp', '')[:10] if result.get('timestamp') else 'Unknown date'}")
        
        if args.debug:
            print(f"   BM25: {result.get('bm25_score', 0):.4f} | Vector: {result.get('vector_score', 0):.4f} | Fused: {result.get('fused_score', 0):.4f}")
        
        if not args.no_summarize and is_gemini_available():
            solr = get_solr_client()
            chunks = solr.get_chunks_by_webpage_id(result["webpage_id"])
            if chunks:
                full_text = "\n\n".join(c.get("text", "") for c in chunks)
                detail_level = detect_detail_level(args.query)
                summary = summarize(args.query, full_text, detail_level)
                if summary:
                    print(f"   Summary: {summary}")
        
        print()


if __name__ == "__main__":
    main()
