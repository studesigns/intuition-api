import os
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Tuple
import tempfile
import re
import asyncio
from concurrent.futures import ThreadPoolExecutor

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain.chains.qa_with_sources import load_qa_with_sources_chain
from langchain.schema import Document
from pypdf import PdfReader
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize FastAPI app
app = FastAPI(title="Compliance Risk Engine API", version="1.0.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins (can restrict to https://intuition-lab.vercel.app later)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global variables for advanced RAG
vector_store = None
all_documents = []  # Store documents with metadata for filtering

# Region configuration mapping
REGION_MAPPING = {
    # US Regions
    "new york": {"regions": ["US", "GLOBAL"], "aliases": ["ny", "newyork"]},
    "california": {"regions": ["US", "GLOBAL"], "aliases": ["ca", "sf", "bay area"]},
    "texas": {"regions": ["US", "GLOBAL"], "aliases": ["tx"]},
    "florida": {"regions": ["US", "GLOBAL"], "aliases": ["fl"]},
    "united states": {"regions": ["US", "GLOBAL"], "aliases": ["usa", "us"]},

    # APAC Regions
    "beijing": {"regions": ["APAC", "GLOBAL"], "aliases": ["china", "cn"]},
    "shanghai": {"regions": ["APAC", "GLOBAL"], "aliases": ["china"]},
    "tokyo": {"regions": ["APAC", "GLOBAL"], "aliases": ["japan", "jp"]},
    "singapore": {"regions": ["APAC", "GLOBAL"], "aliases": ["sg"]},
    "hong kong": {"regions": ["APAC", "GLOBAL"], "aliases": ["hk"]},
    "india": {"regions": ["APAC", "GLOBAL"], "aliases": ["delhi", "mumbai"]},
    "australia": {"regions": ["APAC", "GLOBAL"], "aliases": ["au"]},

    # EMEA Regions
    "london": {"regions": ["EMEA", "GLOBAL"], "aliases": ["uk", "united kingdom"]},
    "germany": {"regions": ["EMEA", "GLOBAL"], "aliases": ["berlin", "de"]},
    "france": {"regions": ["EMEA", "GLOBAL"], "aliases": ["paris", "fr"]},
    "europe": {"regions": ["EMEA", "GLOBAL"], "aliases": ["emea"]},
}

# Risk Officer System Prompt with Universal Jurisdiction Algorithm
RISK_OFFICER_PROMPT = """You are a Compliance Officer in EXTRACTION MODE. Your ONLY role is to:

1. EXTRACT facts that are EXPLICITLY stated in the provided policy documents
2. Do NOT infer, reason, or add contextual knowledge
3. Do NOT synthesize or combine information
4. Return ONLY what the documents explicitly say

═══════════════════════════════════════════════════════════════════════════════
CRITICAL: HALLUCINATION PREVENTION
═══════════════════════════════════════════════════════════════════════════════

YOU MUST NEVER:
- Infer what a document means
- Add contextual knowledge not in the document
- Say "including X" unless X is explicitly listed
- Combine facts from multiple documents to create new conclusions
- Interpret ambiguous language
- Assume document scope extends beyond what is explicitly stated

EXAMPLE OF HALLUCINATION TO AVOID:
❌ WRONG: Document says "No Karaoke in APAC region"
         You say: "including Germany and Japan"
         REASON: This is hallucination! Germany is not in APAC. Document doesn't say "including Germany".

✅ RIGHT: Document says "No Karaoke in APAC region (China, Japan, Vietnam, Indonesia)"
         You say: "No Karaoke in APAC region: China, Japan, Vietnam, Indonesia"
         REASON: You only extracted what was explicitly stated.

═══════════════════════════════════════════════════════════════════════════════
CORE PROTOCOL: UNIVERSAL JURISDICTION CHECK (MANDATORY - EXTRACTION ONLY)
═══════════════════════════════════════════════════════════════════════════════

You ONLY apply a document's rules if the user's location is EXPLICITLY listed in the document scope.

STEP 1: IDENTIFY USER LOCATION
- Extract the user's location (e.g., "Germany", "New York", "Tokyo") from the query.

STEP 2: READ DOCUMENT SCOPE STATEMENTS
- For EACH document chunk, find the EXPLICIT scope statement:
  * "Scope: [list of locations]"
  * "Applies To: [list of locations]"
  * "Geographic Scope: [list of locations]"
  * "This policy covers: [list of locations]"
- Copy the EXACT text of what locations are listed. Do NOT interpret or extend it.

STEP 3: THE MATCH TEST (EXPLICIT ONLY)
- Is [User Location] explicitly listed in the document's scope statement?
  * IF NO: This document does NOT apply. Do not use its rules.
  * IF YES: This document applies. Extract its specific prohibitions/requirements for that location.
  * IF UNCLEAR: Treat as NO. Do not guess or infer document scope.

EXTRACTION EXAMPLE 1 (Explicit Match):
- Document says: "Policy Scope: APAC Region. Prohibited activities: Karaoke, nightclubs"
- User location: "Japan"
- Is Japan explicitly listed or in an explicitly listed region? YES (Japan is in APAC)
- Extract: "In Japan: Karaoke and nightclubs are prohibited"

EXTRACTION EXAMPLE 2 (No Match - Do NOT apply rule):
- Document says: "Policy Scope: APAC Region (China, Japan, Vietnam only)"
- User location: "Germany"
- Is Germany explicitly listed? NO
- Extract: "This document does not apply to Germany"
- Do NOT say: "including Germany" - that's hallucination

EXTRACTION EXAMPLE 3 (Different region):
- Document says: "EMEA Policy: No alcohol at work events"
- User location: "Germany"
- Is Germany in EMEA? YES (explicitly - Europe)
- Extract: "In Germany (EMEA): No alcohol at work events"

═══════════════════════════════════════════════════════════════════════════════
RISK TAXONOMY (ONLY from EXPLICIT document statements)
═══════════════════════════════════════════════════════════════════════════════

🔴 CRITICAL: Document EXPLICITLY states "prohibited", "forbidden", "illegal", "not allowed" for this location
🟠 HIGH: Document EXPLICITLY states "hard limit", "violation", "requires approval", "escalate" for this location
🟡 MODERATE: Document EXPLICITLY states "requires documentation", "requires review", "flag" for this location
🟢 LOW: Document EXPLICITLY states "allowed", "permitted", "approved" OR no restrictions found for this location

═══════════════════════════════════════════════════════════════════════════════
OUTPUT FORMAT (STRICT - RAW JSON ONLY)
═══════════════════════════════════════════════════════════════════════════════

You must return ONLY valid JSON, nothing else.

DO NOT use markdown code blocks (no ```json or ```).
DO NOT include conversational filler or section headers.
DO NOT output any text before or after the JSON.

The response must be directly parseable by JSON.parse() with NO preprocessing.

REQUIRED JSON STRUCTURE:
{
  "risk_level": "CRITICAL" or "HIGH" or "MODERATE" or "LOW",
  "action": "BLOCK" or "ESCALATE" or "FLAG" or "APPROVE",
  "violation_summary": "One sentence: what the document explicitly says applies to this location",
  "detailed_analysis": "Extract ONLY facts from documents. List each document's scope statement and what rules apply to the user's location. If a document doesn't mention the user's location, say so explicitly. Do NOT interpret, infer, or add information."
}

CRITICAL CONSTRAINTS:
- risk_level MUST be one of: CRITICAL, HIGH, MODERATE, LOW
- action MUST be one of: BLOCK, ESCALATE, FLAG, APPROVE
- violation_summary MUST quote or directly reflect the document's EXPLICIT statement
- detailed_analysis MUST be ONLY factual extraction, never inference
- NEVER say "including X" unless X is explicitly listed in the document
- Return ONLY the JSON object, nothing before or after
"""

# ===== QUERY DECOMPOSITION & METADATA ROUTING FUNCTIONS =====

def detect_regions_in_text(text: str) -> Dict[str, List[str]]:
    """
    Detect region mentions in text and map to region categories.

    Returns:
        {
            "entities": ["new york", "beijing"],
            "regions": ["US", "APAC", "GLOBAL"]
        }
    """
    text_lower = text.lower()
    detected_entities = []
    detected_regions = set(["GLOBAL"])  # Global always applies

    for location, config in REGION_MAPPING.items():
        # Check main location name
        if location in text_lower:
            detected_entities.append(location)
            detected_regions.update(config["regions"])
        # Check aliases
        for alias in config.get("aliases", []):
            if re.search(r'\b' + re.escape(alias) + r'\b', text_lower):
                if location not in detected_entities:
                    detected_entities.append(location)
                detected_regions.update(config["regions"])

    return {
        "entities": list(set(detected_entities)),
        "regions": list(detected_regions)
    }


def decompose_query(question: str, llm: ChatOpenAI) -> List[Dict[str, any]]:
    """
    Decompose a query into multiple sub-queries if it contains multiple entities.

    Returns:
        [
            {"entity": "New York", "query": "Gift limit for New York", "regions": ["US", "GLOBAL"]},
            {"entity": "Beijing", "query": "Gift limit for Beijing", "regions": ["APAC", "GLOBAL"]}
        ]
    """
    # Detect regions
    region_detection = detect_regions_in_text(question)
    entities = region_detection["entities"]

    # If only one entity or no entities detected, return single query
    if len(entities) <= 1:
        return [{
            "entity": "General",
            "query": question,
            "regions": region_detection["regions"]
        }]

    # Multiple entities detected - decompose
    decomposition_prompt = f"""Given the following question with multiple geographic references, create separate, focused sub-queries for each location mentioned.

Original Question: {question}

Identified Locations: {", ".join(entities)}

For each location, create a focused sub-query that:
1. Maintains the core compliance question
2. Explicitly names the geographic scope
3. Is independent (can be answered without other sub-queries)

Format your response as a numbered list:
1. [Location]: [Specific sub-query]
2. [Location]: [Specific sub-query]
"""

    response = llm.invoke(decomposition_prompt)
    decomposed_text = response.content

    # Parse the decomposition response
    sub_queries = []
    lines = decomposed_text.split('\n')

    for line in lines:
        if line.strip() and re.match(r'^\d+\.\s', line):
            # Extract the sub-query
            match = re.search(r'^\d+\.\s+\[?([^\]]+)\]?:\s*(.+)$', line)
            if match:
                location = match.group(1).strip()
                query = match.group(2).strip()

                # Get regions for this location
                region_info = detect_regions_in_text(location)

                sub_queries.append({
                    "entity": location,
                    "query": query,
                    "regions": region_info["regions"]
                })

    return sub_queries if sub_queries else [{
        "entity": "General",
        "query": question,
        "regions": region_detection["regions"]
    }]


def filter_documents_by_regions(documents: List[Document], allowed_regions: List[str]) -> List[Document]:
    """
    Filter documents by metadata regions.
    Ensures only documents tagged with allowed regions are used.
    """
    if not allowed_regions:
        return documents

    filtered = []
    for doc in documents:
        doc_regions = doc.metadata.get("regions", ["GLOBAL"])
        # Include if document region matches any allowed region
        if any(region in doc_regions for region in allowed_regions):
            filtered.append(doc)

    return filtered


def extract_metadata_from_content(content: str, chunk: str) -> Dict[str, any]:
    """
    Extract region metadata from document content.
    Analyzes chunk and assigns appropriate regions.
    """
    region_detection = detect_regions_in_text(chunk)
    regions = region_detection["regions"] if region_detection["regions"] else ["GLOBAL"]

    return {
        "regions": regions,
        "source_length": len(chunk),
        "entities": region_detection["entities"]
    }


def extract_json_from_response(response_text: str) -> Dict[str, any]:
    """
    Extract JSON object from LLM response.

    Since STRICT OUTPUT FORMAT requires raw JSON only, this function:
    1. First tries to parse response_text directly as JSON (raw JSON response)
    2. Falls back to markdown json extraction if needed
    3. Returns validated JSON with required fields

    Returns:
        {
            "risk_level": "CRITICAL" | "HIGH" | "MODERATE" | "LOW",
            "action": "BLOCK" | "ESCALATE" | "FLAG" | "APPROVE",
            "violation_summary": "...",
            "detailed_analysis": "..."
        }
    """
    import json

    # Try 1: Parse response as raw JSON directly
    try:
        parsed_json = json.loads(response_text.strip())
        return parsed_json
    except json.JSONDecodeError:
        pass

    # Try 2: Extract JSON from markdown code blocks (fallback for older format)
    try:
        json_match = re.search(r'```json\s*\n?\s*({.*?})\s*\n?```', response_text, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
            parsed_json = json.loads(json_str)
            return parsed_json
    except (json.JSONDecodeError, AttributeError):
        pass

    # Fallback: return empty dict with defaults so frontend can show error gracefully
    return {}


def _retrieve_documents_sync(
    question: str,
    sub_query: Dict[str, any],
    embeddings: OpenAIEmbeddings
) -> List[Document]:
    """
    Synchronous document retrieval for a sub-query with metadata filtering.
    """
    if not vector_store:
        return []

    # Retrieve with similarity search
    relevant_docs = vector_store.similarity_search(sub_query["query"], k=8)

    # Filter by allowed regions to prevent cross-contamination
    filtered_docs = filter_documents_by_regions(
        relevant_docs,
        sub_query["regions"]
    )

    return filtered_docs if filtered_docs else relevant_docs[:3]  # Fallback to top results


async def parallel_retrieve(
    question: str,
    sub_queries: List[Dict[str, any]],
    embeddings: OpenAIEmbeddings
) -> Dict[str, List[Document]]:
    """
    Execute multiple sub-query retrievals in parallel using ThreadPoolExecutor.
    Returns results organized by entity, preventing cross-region contamination.
    """
    loop = asyncio.get_event_loop()
    executor = ThreadPoolExecutor(max_workers=min(len(sub_queries), 4))

    # Create tasks for parallel execution
    tasks = [
        loop.run_in_executor(
            executor,
            _retrieve_documents_sync,
            question,
            sub_query,
            embeddings
        )
        for sub_query in sub_queries
    ]

    # Wait for all tasks to complete
    results_list = await asyncio.gather(*tasks)

    # Map results back to entities
    results = {}
    for sub_query, docs in zip(sub_queries, results_list):
        results[sub_query["entity"]] = docs

    return results


def synthesize_comparative_answer(
    question: str,
    sub_queries: List[Dict[str, any]],
    retrieval_results: Dict[str, List[Document]],
    llm: ChatOpenAI
) -> str:
    """
    Extract compliance facts from retrieved documents for the user's location.
    EXTRACTION MODE ONLY - no synthesis, reasoning, or inference.
    """

    # Build context for each region separately
    region_contexts = {}
    for entity, docs in retrieval_results.items():
        if docs:
            context = "\n\n".join([doc.page_content for doc in docs])
            region_contexts[entity] = context

    if not region_contexts:
        return "No relevant policies found in the knowledge base."

    # Create an extraction prompt (not synthesis)
    extraction_prompt = f"""{RISK_OFFICER_PROMPT}

ORIGINAL QUESTION: {question}

RETRIEVED POLICY DOCUMENTS:
"""

    for entity, context in region_contexts.items():
        extraction_prompt += f"\n[DOCUMENT - {entity.upper()}]:\n{context}\n"

    extraction_prompt += f"""
EXTRACTION TASK:
You are in EXTRACTION MODE. Do NOT synthesize or provide recommendations.

Your task:
1. Find the explicit scope statement in each document
2. Check if the user's location is explicitly mentioned in that scope
3. If YES: Extract what policies apply to that location
4. If NO: State that document does not apply

Do NOT combine information from multiple documents.
Do NOT infer document scope beyond what is explicitly stated.
Do NOT add contextual knowledge.

Return ONLY the JSON object with extracted facts."""

    response = llm.invoke(extraction_prompt)
    return response.content


@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "operational",
        "service": "Compliance Risk Engine API",
        "version": "1.0.0"
    }


@app.post("/upload")
async def upload_policies(files: List[UploadFile] = File(...)):
    """
    Upload PDF policy documents to build the knowledge base with metadata.

    Extracts region information from documents and tags each chunk accordingly.

    Args:
        files: List of PDF files to upload

    Returns:
        {
            "status": "success",
            "chunks": number of text chunks created,
            "files_processed": number of files processed,
            "regions_detected": detected regions
        }
    """
    global vector_store, all_documents

    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    try:
        # Check for OpenAI API key
        if not os.getenv("OPENAI_API_KEY"):
            raise HTTPException(
                status_code=500,
                detail="OpenAI API key not configured"
            )

        all_text = ""
        files_processed = 0
        all_regions = set()

        # Extract text from all PDF files
        for file in files:
            if not file.filename.endswith('.pdf'):
                continue

            # Read PDF content
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
                content = await file.read()
                tmp.write(content)
                tmp.flush()

                # Parse PDF
                pdf_reader = PdfReader(tmp.name)
                for page in pdf_reader.pages:
                    all_text += page.extract_text() + "\n"

                files_processed += 1

            # Clean up temp file
            os.unlink(tmp.name)

        if not all_text:
            raise HTTPException(
                status_code=400,
                detail="No text could be extracted from the PDF files"
            )

        # Split text into chunks
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            separators=["\n\n", "\n", " ", ""]
        )
        chunks = text_splitter.split_text(all_text)

        if not chunks:
            raise HTTPException(
                status_code=400,
                detail="No text chunks created from PDFs"
            )

        # Create documents with metadata for each chunk
        documents = []
        for chunk in chunks:
            # Extract region metadata from chunk
            metadata = extract_metadata_from_content(all_text, chunk)
            all_regions.update(metadata["regions"])

            # Create LangChain Document with metadata
            doc = Document(
                page_content=chunk,
                metadata=metadata
            )
            documents.append(doc)

        # Create embeddings and vector store with metadata
        embeddings = OpenAIEmbeddings(
            model="text-embedding-ada-002",
            openai_api_key=os.getenv("OPENAI_API_KEY")
        )

        vector_store = FAISS.from_documents(documents, embeddings)
        all_documents = documents

        return {
            "status": "success",
            "chunks": len(chunks),
            "files_processed": files_processed,
            "regions_detected": list(all_regions),
            "message": f"Successfully processed {files_processed} PDF file(s) into {len(chunks)} chunks with metadata routing"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing files: {str(e)}")


@app.post("/query")
async def query_policies(request: dict):
    """
    Query the compliance policies with advanced query decomposition and metadata routing.

    Handles multi-region queries by:
    1. Decomposing the question into region-specific sub-queries
    2. Retrieving documents with metadata filtering (no cross-region pollution)
    3. Running sub-queries in parallel for efficiency
    4. Synthesizing results into a comparative analysis

    Args:
        request: JSON body with "question" key

    Returns:
        {
            "answer": "Risk Officer's comparative analysis",
            "sources": ["relevant policy sections"],
            "compliance_status": "COMPLIANT|RISK DETECTED|REQUIRES REVIEW",
            "query_decomposition": [{"entity": "...", "query": "...", "regions": [...]}],
            "regions_analyzed": ["US", "APAC", "GLOBAL"]
        }
    """
    global vector_store

    if not vector_store:
        raise HTTPException(
            status_code=400,
            detail="No policies uploaded. Please upload policy documents first via /upload endpoint"
        )

    question = request.get("question")
    if not question:
        raise HTTPException(status_code=400, detail="Question field is required")

    try:
        # Check for OpenAI API key
        if not os.getenv("OPENAI_API_KEY"):
            raise HTTPException(
                status_code=500,
                detail="OpenAI API key not configured"
            )

        # Initialize embeddings and LLM
        embeddings = OpenAIEmbeddings(
            model="text-embedding-ada-002",
            openai_api_key=os.getenv("OPENAI_API_KEY")
        )

        llm = ChatOpenAI(
            model="gpt-3.5-turbo",
            temperature=0,  # Deterministic for compliance
            openai_api_key=os.getenv("OPENAI_API_KEY")
        )

        # ===== STEP 1: QUERY DECOMPOSITION =====
        sub_queries = decompose_query(question, llm)

        # ===== STEP 2: PARALLEL RETRIEVAL WITH METADATA FILTERING =====
        retrieval_results = await parallel_retrieve(question, sub_queries, embeddings)

        # If no results from any sub-query, return no results
        if not retrieval_results or all(not docs for docs in retrieval_results.values()):
            return {
                "answer": "No relevant policies found in the knowledge base for the specified regions.",
                "sources": [],
                "compliance_status": "REQUIRES REVIEW",
                "query_decomposition": sub_queries,
                "regions_analyzed": detect_regions_in_text(question)["regions"]
            }

        # ===== STEP 3: SYNTHESIS =====
        # Generate a single comprehensive answer using the isolated region contexts
        answer = synthesize_comparative_answer(
            question,
            sub_queries,
            retrieval_results,
            llm
        )

        # Collect all sources from all regions
        all_docs = []
        regions_analyzed = set()
        for entity, docs in retrieval_results.items():
            all_docs.extend(docs)
            if docs:
                for doc in docs:
                    regions_analyzed.update(doc.metadata.get("regions", ["GLOBAL"]))

        sources = [doc.page_content[:200] + "..." for doc in all_docs[:5]]  # Top 5

        # ===== Extract JSON Classification from Response =====
        # The LLM includes a JSON block with violation_summary and other fields
        json_classification = extract_json_from_response(answer)

        violation_summary = json_classification.get(
            "violation_summary",
            "Compliance assessment pending..."
        )

        # Determine compliance status from answer
        compliance_status = "COMPLIANT"
        if "RISK DETECTED" in answer.upper():
            compliance_status = "RISK DETECTED"
        elif "REQUIRES REVIEW" in answer.upper():
            compliance_status = "REQUIRES REVIEW"

        return {
            "answer": answer,
            "sources": sources,
            "compliance_status": compliance_status,
            "documents_searched": len(all_docs),
            "query_decomposition": sub_queries,
            "regions_analyzed": list(regions_analyzed),
            "decomposition_note": f"Query decomposed into {len(sub_queries)} sub-queries with isolated metadata routing",
            # ===== New: Structured JSON fields for frontend =====
            "violation_summary": violation_summary,
            "risk_classification": json_classification
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing query: {str(e)}")


@app.get("/status")
async def status():
    """Check if policies are loaded and metadata routing is active"""
    regions_available = set()
    for doc in all_documents:
        regions_available.update(doc.metadata.get("regions", ["GLOBAL"]))

    return {
        "policies_loaded": vector_store is not None,
        "status": "ready" if vector_store else "awaiting_policies",
        "total_documents": len(all_documents),
        "regions_available": list(regions_available),
        "metadata_routing_active": vector_store is not None,
        "supported_regions": list(REGION_MAPPING.keys())
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
