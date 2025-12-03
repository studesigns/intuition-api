#!/usr/bin/env python3
"""Upload test documents to the API"""

import requests
import os
from pathlib import Path

API_URL = "https://intuition-api.onrender.com"
TEST_DOCS_PATH = "/home/stu/Projects/intuition-api/test_docs"

def upload_documents():
    """Upload all PDF files from test_docs directory"""

    # Find all PDF files
    pdf_files = list(Path(TEST_DOCS_PATH).glob("*.pdf"))

    if not pdf_files:
        print(f"✗ No PDF files found in {TEST_DOCS_PATH}")
        return False

    print(f"Found {len(pdf_files)} PDF files to upload:")
    for pdf in pdf_files:
        print(f"  - {pdf.name}")

    # Prepare files for upload
    files = []
    for pdf_path in pdf_files:
        with open(pdf_path, "rb") as f:
            files.append(("files", (pdf_path.name, f, "application/pdf")))

    print(f"\nUploading to {API_URL}/upload...")

    try:
        # Read files fresh for the request
        files_list = [
            ("files", (pdf.name, open(pdf, "rb"), "application/pdf"))
            for pdf in pdf_files
        ]

        response = requests.post(
            f"{API_URL}/upload",
            files=files_list,
            timeout=60
        )

        # Close files
        for _, (_, f, _) in files_list:
            f.close()

        if response.status_code == 200:
            data = response.json()
            print(f"\n✓ Upload successful!")
            print(f"  Files processed: {data.get('files_processed', 0)}")
            print(f"  Chunks created: {data.get('chunks', 0)}")
            print(f"  Regions detected: {data.get('regions_detected', [])}")
            return True
        else:
            print(f"\n✗ Upload failed with status {response.status_code}")
            print(f"Response: {response.text[:500]}")
            return False

    except Exception as e:
        print(f"\n✗ Error uploading: {e}")
        return False


if __name__ == "__main__":
    success = upload_documents()
    exit(0 if success else 1)
