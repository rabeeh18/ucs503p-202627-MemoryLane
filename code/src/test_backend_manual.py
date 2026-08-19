#!/usr/bin/env python3
"""
Manual backend test — hits the FastAPI endpoints directly so you don't
need Tampermonkey/a browser to check that saving and querying work.

Usage:
    python test_backend_manual.py
"""

import requests
import json
import time

BACKEND_URL = "http://localhost:8000"
HEALTH_CHECK_URL = f"{BACKEND_URL}/health"
SAVE_MEMORY_URL = f"{BACKEND_URL}/memory"

# one normal-length article, one similar-but-distinct topic, one overlapping
# topic, and one totally unrelated page — enough to sanity-check that
# similarity search actually discriminates between them
TEST_WEBPAGES = [
    {
        "url": "https://example.com/ppo-explained",
        "title": "PPO: Proximal Policy Optimization",
        "content": """
        Proximal Policy Optimization (PPO) is a reinforcement learning algorithm 
        that uses gradient-based policy optimization. PPO prevents large policy updates 
        by clipping the objective function. This makes the algorithm stable and efficient.
        
        The key idea is to take multiple gradient steps on the same batch of data,
        but limit each step to stay within a trust region. This is done using a 
        clipped surrogate objective.
        
        PPO is widely used because it's sample-efficient and stable compared to 
        other policy gradient methods like A3C or TRPO.
        """
    },
    {
        "url": "https://example.com/reinforcement-learning",
        "title": "Reinforcement Learning Basics",
        "content": """
        Reinforcement learning (RL) is a type of machine learning where an agent 
        learns to make decisions by interacting with an environment. The agent 
        receives rewards or penalties and learns to maximize cumulative reward.
        
        Key concepts:
        - Agent: the learner
        - Environment: the world the agent interacts with
        - State: the current situation
        - Action: what the agent can do
        - Reward: feedback signal
        - Policy: mapping from states to actions
        
        RL is used in robotics, games, autonomous vehicles, and many other domains.
        """
    },
    {
        "url": "https://example.com/deep-learning",
        "title": "Deep Learning: Neural Networks",
        "content": """
        Deep learning is a subset of machine learning that uses neural networks 
        with multiple layers (hence "deep"). These networks can learn hierarchical 
        representations of data.
        
        A neural network consists of:
        - Input layer: receives data
        - Hidden layers: process data
        - Output layer: produces predictions
        
        Training uses backpropagation to adjust weights and minimize loss.
        
        Deep learning excels at computer vision, natural language processing, 
        and other complex tasks.
        """
    },
    {
        "url": "https://example.com/cooking-guide",
        "title": "How to Make Italian Pasta",
        "content": """
        Making fresh pasta from scratch is easier than you think. Here's how:
        
        Ingredients:
        - 2 cups all-purpose flour
        - 3 eggs
        - Salt to taste
        - Olive oil
        
        Steps:
        1. Mix flour and salt
        2. Create a well in the center
        3. Add beaten eggs
        4. Mix and knead until smooth
        5. Let rest for 30 minutes
        6. Roll out and cut into desired shape
        7. Cook in boiling salted water for 2-3 minutes
        
        Serve with your favorite sauce!
        """
    }
]


def print_section(title):
    print("\n" + "="*80)
    print(f"  {title}")
    print("="*80 + "\n")


def test_health_check():
    print("Testing health check...")
    try:
        response = requests.get(HEALTH_CHECK_URL, timeout=5)
        response.raise_for_status()

        data = response.json()
        print(f"✓ Backend is running")
        print(f"  Status: {data.get('status')}")
        print(f"  Message: {data.get('message')}")
        return True
    except requests.exceptions.ConnectionError:
        print("✗ Cannot connect to backend")
        print(f"  Make sure FastAPI is running on {BACKEND_URL}")
        print(f"  Command: uvicorn backend.main:app --reload")
        return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def test_save_webpage(webpage_data):
    print(f"Saving: {webpage_data['title']}")
    print(f"  URL: {webpage_data['url']}")
    print(f"  Content length: {len(webpage_data['content'])} characters")

    try:
        response = requests.post(
            SAVE_MEMORY_URL,
            json=webpage_data,
            timeout=30  # embedding generation can take a moment on first call
        )
        response.raise_for_status()

        result = response.json()
        if result.get("success"):
            print(f"✓ Saved successfully")
            print(f"  Memory ID: {result.get('metadata', {}).get('id')}")
            print(f"  Timestamp: {result.get('metadata', {}).get('timestamp')}")
            return True
        else:
            print(f"✗ Backend returned error: {result.get('message')}")
            return False
    except requests.exceptions.Timeout:
        print("✗ Request timed out (embedding generation taking long?)")
        return False
    except requests.exceptions.ConnectionError:
        print("✗ Cannot connect to backend")
        return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def test_all_webpages():
    print_section("SAVING TEST WEBPAGES")

    success_count = 0
    for i, webpage in enumerate(TEST_WEBPAGES, 1):
        print(f"\n[{i}/{len(TEST_WEBPAGES)}]")
        if test_save_webpage(webpage):
            success_count += 1
        time.sleep(1)  # don't hammer the embedding model back-to-back

    print(f"\n✓ Successfully saved {success_count}/{len(TEST_WEBPAGES)} webpages")
    return success_count == len(TEST_WEBPAGES)


def test_queries():
    print_section("SEARCHING MEMORIES")

    # each query paired with what we expect to come back, so a mismatch
    # is obvious at a glance instead of needing to reason about it
    queries = [
        ("policy gradient methods", "Should match: PPO, RL articles"),
        ("how to make pasta", "Should match: Cooking article"),
        ("machine learning and neural networks", "Should match: Deep Learning, RL articles"),
        ("stable training algorithms", "Should match: PPO article"),
        ("something about pizza", "Should match: Nothing or low similarity"),
    ]

    from sentence_transformers import SentenceTransformer
    import chromadb

    print("Loading embedding model...")
    try:
        model = SentenceTransformer("all-MiniLM-L6-v2")
        print("✓ Model loaded")
    except Exception as e:
        print(f"✗ Failed to load model: {e}")
        return False

    print("\nConnecting to ChromaDB...")
    try:
        client = chromadb.PersistentClient(path="./chroma_db")
        collection = client.get_collection("memorylane")
        count = collection.count()
        print(f"✓ Connected to ChromaDB ({count} records)")
    except Exception as e:
        print(f"✗ Failed to connect to ChromaDB: {e}")
        return False

    for query, expected in queries:
        print(f"\n[Query] {query}")
        print(f"[Expected] {expected}")

        try:
            query_embedding = model.encode(query)
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=3,
                include=["metadatas", "distances"]
            )

            if results["ids"][0]:
                print("[Results]")
                for i, (metadata, distance) in enumerate(zip(
                    results["metadatas"][0],
                    results["distances"][0]
                ), 1):
                    similarity = 1 - distance
                    title = metadata.get("title", "Unknown")
                    print(f"  {i}. {title} (similarity: {similarity:.2%})")
            else:
                print("[Results] No matches found")
        except Exception as e:
            print(f"✗ Search error: {e}")

    return True


def main():
    print("\n" + "="*80)
    print("  MEMORYLANE - BACKEND TEST SUITE")
    print("="*80)

    print_section("PHASE 1: HEALTH CHECK")
    if not test_health_check():
        print("\n✗ Backend is not running!")
        print("  Start it with: uvicorn backend.main:app --reload")
        return False

    print_section("PHASE 2: SAVE WEBPAGES")
    input("\nPress Enter to start saving test webpages...")
    if not test_all_webpages():
        print("\n✗ Failed to save webpages")
        return False

    print_section("PHASE 3: QUERY")
    input("\nPress Enter to start searching...")
    if not test_queries():
        print("\n✗ Query testing failed")
        return False

    print_section("TEST COMPLETE")
    print("✓ All tests passed!")
    print("\nNext steps:")
    print("1. Install Tampermonkey extension in Chrome")
    print("2. Install MemoryLane userscript in Tampermonkey")
    print("3. Visit a webpage and click 'Save to MemoryLane'")
    print("4. Search using: python query.py \"search term\"")

    return True


if __name__ == "__main__":
    try:
        success = main()
        exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n✗ Test interrupted by user")
        exit(1)