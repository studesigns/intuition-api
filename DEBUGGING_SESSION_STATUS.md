# Debugging Session Status - December 3, 2025

## Objective
Fix hallucination prevention system so that:
- Germany Karaoke queries return LOW risk (allowed globally)
- Japan Karaoke queries return CRITICAL risk (prohibited in APAC)
- No mixing of APAC policies into non-APAC queries

## Root Causes Identified & Fixed

### ✅ FIXED: Per-File PDF Processing
**Problem**: All 3 PDF files were being concatenated into one `all_text` blob before chunking. This caused metadata extraction to see ALL documents' content at once, tagging all chunks based on combined content.

**Impact**: Every chunk was being tagged with metadata from all 3 documents.

**Solution** (Commit 31f697d):
- Process each PDF file separately in the upload endpoint
- Pass individual file_text to metadata extraction, not combined text
- Lines 625-670 in main.py: Refactored to loop through files individually

### ✅ FIXED: Fallback Query Decomposition
**Problem**: `decompose_query()` fallback was returning `["GLOBAL", "APAC", "EMEA", "US"]` for ANY error, contaminating all queries.

**Impact**: Germany queries were requesting documents from all regions, not just EMEA/GLOBAL.

**Solution** (Commit 31f697d):
- Changed fallback to return only `["GLOBAL"]` when errors occur
- Lines 141-170: Safer fallback for query decomposition

### ✅ FIXED: Document Retrieval Fallback
**Problem**: `_retrieve_documents_sync()` was returning unfiltered top-3 results when filtering removed all documents.

**Impact**: If APAC docs dominated the similarity search for "karaoke", they were still returned for Germany queries.

**Solution** (Commit 31f697d):
- Modified to return empty list instead of unfiltered results
- Try to get 20 more docs and filter again before giving up
- Lines 432-451: Smarter fallback logic with debug mode

### ✅ PARTIALLY FIXED: Metadata Extraction
**Problem**: Metadata extraction was too strict and falling back to region_detection, which always includes GLOBAL.

**Solutions Applied**:
1. Check document-level scope (content parameter) for scope indicators
2. Tag APAC documents with `["APAC"]` only (not mixed)
3. Default to `["GLOBAL"]` for documents without specific region markers
4. Lines 237-269: Improved metadata detection with multiple fallbacks

## Remaining Issues

### ❓ Vector Store Retrieval Not Working
**Status**: Under investigation

**Symptoms**:
- Documents upload successfully (10 chunks created)
- Queries return "No relevant policies found"
- Even generic queries return 0 documents
- GLOBAL queries should match but don't

**Possible Causes**:
1. Vector store being cleared or not persisting between requests
2. Filter logic still too strict even with debug fallback
3. Server reload losing in-memory vector store
4. Issue with FAISS index creation in new per-file approach

**Next Steps**:
1. Add persistence to vector store (save to disk)
2. Add detailed logging to understand retrieval flow
3. Test `similarity_search()` directly to verify docs are in store
4. Check if metadata tags are correct on stored documents

## Test Case Status

### Germany Karaoke (EMEA + GLOBAL regions)
- Expected: LOW risk, documents should match GLOBAL policy
- Current: "No relevant policies found"
- Status: ❌ BLOCKED BY RETRIEVAL ISSUE

### Japan Karaoke (APAC + GLOBAL regions)
- Expected: CRITICAL risk, documents should match APAC policy
- Current: Not yet tested (blocked by retrieval issue)
- Status: ⏳ PENDING

## Code Changes Made

**File**: `/home/stu/Projects/intuition-api/main.py`

**Commits**:
- `31f697d`: Fix document metadata tagging and per-file processing

**Key Changes**:
1. Upload endpoint (lines 621-676): Per-file processing
2. Metadata extraction (lines 237-269): Improved scope detection
3. Query decomposition (lines 141-170): Safer fallback
4. Document retrieval (lines 432-451): Smarter filtering logic
5. Response building (lines 689, 692): Fixed chunk reference

## Architecture Overview (Post-Fix)

```
PDF Upload
  ↓
Per-File Processing
  ├── File 1 → Extract text
  ├── File 2 → Extract text
  └── File 3 → Extract text
  ↓
Per-File Chunking (separate for each)
  ├── Global Doc 1 → 3 chunks (tagged GLOBAL)
  ├── APAC Doc → 4 chunks (tagged APAC)
  └── Global Doc 2 → 3 chunks (tagged GLOBAL)
  ↓
Metadata Tagging (per-file context)
  ├── "APAC" documents → ["APAC"]
  └── Other → ["GLOBAL"]
  ↓
Vector Store (FAISS)
  ↓
Query
  ↓
Region Detection ("Germany" → ["EMEA", "GLOBAL"])
  ↓
Document Retrieval + Filtering
  ├── Search k=8
  ├── Filter by ["EMEA", "GLOBAL"]
  └── Fallback: Search k=20, filter, or return unfiltered (debug)
  ↓
LLM Synthesis
```

## Quick Reference

### To Resume Work:
1. Focus on vector store persistence
2. Add logging to `_retrieve_documents_sync()` to understand flow
3. Test `vector_store.similarity_search()` directly
4. Verify metadata is correct on stored documents:
   - APAC docs should have `metadata["regions"] = ["APAC"]`
   - Global docs should have `metadata["regions"] = ["GLOBAL"]`

### Critical Functions:
- `extract_metadata_from_content()` (lines 225-275): Assign regions to chunks
- `filter_documents_by_regions()` (lines 175-213): Filter docs by query region
- `_retrieve_documents_sync()` (lines 412-451): Retrieve & filter docs
- `upload_policies()` (lines 613-696): Upload & process PDFs

### Test Documents:
- `/home/stu/Projects/intuition-api/test_docs/*.pdf` (3 files, 10 total chunks)
- Comprehensive test suite: `/home/stu/Projects/intuition-api/execute_comprehensive_tests.py`

## Expected Test Results (Once Fixed)

| Query | Regions | Expected Risk | Status |
|-------|---------|---|---|
| Karaoke in Germany | EMEA, GLOBAL | LOW | ⏳ |
| Karaoke in Japan | APAC, GLOBAL | CRITICAL | ⏳ |
| Nightclub in China | APAC, GLOBAL | CRITICAL | ⏳ |
| Golf in France | EMEA, GLOBAL | LOW | ⏳ |
| Casino in Singapore | APAC, GLOBAL | CRITICAL | ⏳ |

---

*Last Updated: December 3, 2025 - 10:30 UTC*
*Session: Deep debugging of metadata extraction and document retrieval pipeline*
*Blocker: Vector store retrieval returning no documents*
