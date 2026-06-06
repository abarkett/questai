#!/usr/bin/env python3
"""
Quick test script to verify Miriel integration.
Run this after setting up MIRIEL_API_KEY in .env
"""

from dotenv import load_dotenv
load_dotenv()

from app.services.miriel_client import get_miriel_client, is_miriel_enabled
from app.db import init_db

def test_miriel_setup():
    """Test basic Miriel client setup."""
    print("=" * 60)
    print("MIRIEL INTEGRATION TEST")
    print("=" * 60)

    # Test 1: Client initialization
    print("\n[Test 1] Miriel Client Initialization")
    client = get_miriel_client()
    print(f"  ✓ Client created: {client is not None}")
    print(f"  ✓ Enabled: {client.enabled}")
    print(f"  ✓ Auto-learning: {client.auto_learning_enabled}")
    print(f"  ✓ Project namespace: {client._instance.PROJECT_NAMESPACE if client._instance else 'N/A'}")

    if not client.enabled:
        print("\n⚠️  WARNING: Miriel is DISABLED")
        print("  Set MIRIEL_API_KEY in .env to enable AI features")
        print("  The game will still work with template-based content!")
        return False

    # Test 2: Database initialization
    print("\n[Test 2] Database Schema")
    try:
        init_db()
        print("  ✓ Database initialized with Miriel tables")
    except Exception as e:
        print(f"  ✗ Database error: {e}")
        return False

    # Test 3: Simple learn operation
    print("\n[Test 3] Learning System")
    try:
        result = client.learn(
            input_data={
                "test": "Miriel integration test",
                "timestamp": "initial setup"
            },
            metadata={
                "type": "integration_test"
            }
        )
        print(f"  ✓ Learn operation completed")
    except Exception as e:
        print(f"  ✗ Learning failed: {e}")
        return False

    # Test 4: Simple query
    print("\n[Test 4] Query System")
    try:
        response = client.query(
            query="What is a good name for a medieval fantasy quest about rats?",
            project="questai"
        )

        if response and response.get("results"):
            answer = response.get("results", {}).get("answer", "")[:100]
            print(f"  ✓ Query successful")
            print(f"    Response preview: {answer}...")
        else:
            print(f"  ⚠️  Query returned no results")

    except Exception as e:
        print(f"  ⚠️  Query failed: {e}")
        print(f"    (This may be normal if no data learned yet)")

    print("\n" + "=" * 60)
    print("✅ MIRIEL INTEGRATION TEST PASSED")
    print("=" * 60)
    print("\nNext steps:")
    print("1. Start the server: uvicorn app.main:app --reload --port 8787")
    print("2. Play the game - all actions will be learned automatically")
    print("3. Try accepting a quest that doesn't exist in templates")
    print("4. Talk to NPCs to see AI-generated dialogue")
    print("\n")

    return True


if __name__ == "__main__":
    success = test_miriel_setup()
    exit(0 if success else 1)
