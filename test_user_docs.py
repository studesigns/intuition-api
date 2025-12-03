#!/usr/bin/env python3
"""Test with actual user compliance documents"""

import requests
import json
import os
from pathlib import Path

API_URL = "https://intuition-api.onrender.com"
USER_DOCS_PATH = "/home/stu/Projects/intuition lab test docs for compliance"

def upload_user_documents():
    """Upload user's actual compliance documents"""

    pdf_files = list(Path(USER_DOCS_PATH).glob("*.pdf"))

    if not pdf_files:
        print(f"✗ No PDF files found in {USER_DOCS_PATH}")
        return False

    print(f"Found {len(pdf_files)} user compliance PDFs:")
    for pdf in pdf_files:
        print(f"  - {pdf.name}")

    files_list = [
        ("files", (pdf.name, open(pdf, "rb"), "application/pdf"))
        for pdf in pdf_files
    ]

    print(f"\nUploading to {API_URL}/upload...")

    try:
        response = requests.post(
            f"{API_URL}/upload",
            files=files_list,
            timeout=60
        )

        for _, (_, f, _) in files_list:
            f.close()

        if response.status_code == 200:
            data = response.json()
            print(f"✓ Upload successful!")
            print(f"  Files: {data.get('files_processed', 0)}")
            print(f"  Chunks: {data.get('chunks', 0)}")
            print(f"  Regions: {data.get('regions_detected', [])}")
            return True
        else:
            print(f"✗ Upload failed: {response.status_code}")
            print(response.text[:500])
            return False

    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def test_germany_japan_karaoke():
    """Test the Germany + Japan karaoke question"""

    question = """I have two client entertainment events coming up.
    First, I am taking a client in Germany to a Karaoke bar.
    Second, I am taking a client in Japan to a karaoke bar.
    Please classify the risk for each event."""

    print(f"\n{'='*70}")
    print("TESTING: Germany + Japan Karaoke")
    print(f"{'='*70}")
    print(f"\nQuestion: {question}\n")

    try:
        response = requests.post(
            f"{API_URL}/query",
            json={"question": question},
            timeout=30
        )

        if response.status_code != 200:
            print(f"✗ Query failed: {response.status_code}")
            print(response.text[:500])
            return False

        data = response.json()

        print("RAW RESPONSE FIELDS:")
        print(f"  - Has 'answer': {bool(data.get('answer'))}")
        print(f"  - Has 'user_friendly_output': {bool(data.get('user_friendly_output'))}")
        print(f"  - Has 'risk_classification': {bool(data.get('risk_classification'))}")
        print(f"  - Has 'query_decomposition': {bool(data.get('query_decomposition'))}")

        print(f"\n{'='*70}")
        print("USER-FRIENDLY OUTPUT:")
        print(f"{'='*70}")
        output = data.get('user_friendly_output', data.get('answer', 'NO OUTPUT'))
        print(output)

        print(f"\n{'='*70}")
        print("ANALYSIS VERIFICATION:")
        print(f"{'='*70}")

        # Check Germany
        if "GERMANY" in output.upper():
            print("✓ Germany analysis present")
            if "LOW" in output or "APPROVE" in output or "PERMITTED" in output.upper():
                print("  ✓ Germany shows LOW/APPROVE (CORRECT)")
            elif "CRITICAL" in output or "BLOCK" in output:
                print("  ✗ Germany shows CRITICAL/BLOCK (INCORRECT - should be LOW/APPROVE)")
            else:
                print("  ? Germany risk level unclear")
        else:
            print("✗ Germany analysis MISSING")

        # Check Japan (find Tokyo or Japan section specifically)
        if "JAPAN" in output.upper() or "TOKYO" in output.upper():
            print("✓ Japan analysis present")
            # Extract the Tokyo/Japan section to check risk level
            tokyo_section = output[output.upper().find("TOKYO"):] if "TOKYO" in output.upper() else ""
            if "TOKYO:" in output:
                tokyo_start = output.upper().find("TOKYO:")
                # Find next location marker or end of string
                next_marker = output.find("\n\n", tokyo_start + 6)
                if next_marker == -1:
                    next_marker = len(output)
                tokyo_section = output[tokyo_start:next_marker]

            # Check what risk level appears in Tokyo section
            if "CRITICAL" in tokyo_section:
                print(f"  ✓ Japan shows CRITICAL (CORRECT)")
            elif "HIGH" in tokyo_section and "BLOCK" in tokyo_section:
                print(f"  ⚠ Japan shows HIGH/BLOCK (Should be CRITICAL/BLOCK)")
            elif "LOW" in tokyo_section or "APPROVE" in tokyo_section:
                print(f"  ✗ Japan shows LOW/APPROVE (INCORRECT - should be CRITICAL/BLOCK)")
            else:
                print(f"  ? Japan risk level unclear in: {tokyo_section[:100]}")
        else:
            print("✗ Japan analysis MISSING")

        print(f"\n{'='*70}")
        print("RESPONSE STRUCTURE:")
        print(f"{'='*70}")
        print(json.dumps({
            "compliance_status": data.get('compliance_status'),
            "query_decomposition": [
                {"entity": d.get('entity'), "regions": d.get('regions')}
                for d in data.get('query_decomposition', [])
            ],
            "regions_analyzed": data.get('regions_analyzed')
        }, indent=2))

        return True

    except Exception as e:
        print(f"✗ Error: {e}")
        return False


if __name__ == "__main__":
    print(f"\n{'='*70}")
    print("USER COMPLIANCE DOCUMENT TEST")
    print(f"{'='*70}\n")

    if upload_user_documents():
        print("\nWaiting for vector store update...")
        import time
        time.sleep(2)
        test_germany_japan_karaoke()
    else:
        print("Failed to upload documents")
