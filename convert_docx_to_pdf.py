#!/usr/bin/env python3
"""
Convert DOCX files to PDF for backend ingestion
"""

import subprocess
import os
from pathlib import Path

def convert_docx_to_pdf(docx_path):
    """Convert DOCX to PDF using LibreOffice"""
    docx_path = Path(docx_path)
    output_dir = docx_path.parent

    try:
        # Use LibreOffice headless conversion
        result = subprocess.run([
            'libreoffice',
            '--headless',
            '--convert-to', 'pdf',
            '--outdir', str(output_dir),
            str(docx_path)
        ], capture_output=True, timeout=30)

        if result.returncode == 0:
            pdf_path = output_dir / docx_path.stem + ".pdf"
            if pdf_path.exists():
                return str(pdf_path)

        return None
    except FileNotFoundError:
        print("LibreOffice not found. Trying alternative method...")
        return None
    except Exception as e:
        print(f"Error: {e}")
        return None

def main():
    doc_dir = Path("/home/stu/Projects/intuition-api/test_docs")
    docx_files = list(doc_dir.glob("*.docx"))

    print(f"Found {len(docx_files)} DOCX files")

    for docx_file in docx_files:
        print(f"\nConverting: {docx_file.name}")
        pdf_path = convert_docx_to_pdf(str(docx_file))

        if pdf_path:
            print(f"✓ Created: {pdf_path}")
        else:
            print(f"✗ Failed to convert: {docx_file.name}")

    # List resulting PDFs
    print(f"\n{'='*60}")
    print("PDF Files Available:")
    pdf_files = list(doc_dir.glob("*.pdf"))
    for pdf in pdf_files:
        size_kb = pdf.stat().st_size / 1024
        print(f"  - {pdf.name} ({size_kb:.1f} KB)")

    return len(pdf_files) > 0

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
