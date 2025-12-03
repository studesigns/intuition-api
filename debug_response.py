#!/usr/bin/env python3
"""Debug script to examine raw API responses"""

import requests
import json

API_URL = "https://intuition-api.onrender.com"

def debug_multilocation_query():
    """Test and debug the multi-location query"""

    question = """I have two client entertainment events.
    First, I am taking a client in Germany to a Karaoke bar.
    Second, I am taking a client in Japan to a karaoke bar.
    Please classify the risk for each event."""

    print(f"\n{'='*70}")
    print("DEBUGGING MULTI-LOCATION QUERY")
    print(f"{'='*70}\n")

    print(f"Question: {question}\n")

    response = requests.post(
        f"{API_URL}/query",
        json={"question": question},
        timeout=30
    )

    data = response.json()

    print(f"Status Code: {response.status_code}")
    print(f"\nFull Response (pretty-printed):\n")
    print(json.dumps(data, indent=2))

    print(f"\n{'='*70}")
    print("DETAILED ANALYSIS")
    print(f"{'='*70}\n")

    print(f"Answer (raw):\n{data.get('answer', 'N/A')}")
    print(f"\n{'-'*70}\n")

    print(f"Risk Classification:\n")
    print(json.dumps(data.get('risk_classification', {}), indent=2))

    print(f"\n{'-'*70}\n")

    print(f"Query Decomposition:")
    for i, sub_query in enumerate(data.get('query_decomposition', []), 1):
        print(f"  {i}. Entity: {sub_query.get('entity')}, Regions: {sub_query.get('regions')}")

    print(f"\nUser-Friendly Output:\n")
    print(data.get('user_friendly_output', 'N/A'))


def debug_single_location_query(location):
    """Test single location query"""

    question = f"Can I take a client to karaoke in {location}?"

    print(f"\n{'='*70}")
    print(f"DEBUGGING SINGLE LOCATION: {location}")
    print(f"{'='*70}\n")

    response = requests.post(
        f"{API_URL}/query",
        json={"question": question},
        timeout=30
    )

    data = response.json()

    print(f"Risk Level: {data.get('risk_classification', {}).get('risk_level', 'UNKNOWN')}")
    print(f"Action: {data.get('risk_classification', {}).get('action', 'UNKNOWN')}")
    print(f"\nUser-Friendly Output:\n")
    print(data.get('user_friendly_output', 'N/A'))


if __name__ == "__main__":
    debug_multilocation_query()
    print("\n" + "="*70 + "\n")
    debug_single_location_query("Germany")
    print("\n" + "="*70 + "\n")
    debug_single_location_query("Japan")
