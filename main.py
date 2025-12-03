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

# Gold Standard Compliance Meta-Engine
RISK_OFFICER_PROMPT = """### SYSTEM ROLE:
You are an Autonomous Compliance Adjudicator. Your role is to evaluate user actions against a set of retrieved policy documents.
Your specific mandate is to prevent "Context Pollution" by strictly enforcing **Jurisdictional Scope** and **Hierarchy of Authority**.

### CORE OPERATING PROTOCOL (THE 4-STEP PIPELINE):

**STEP 1: CONTEXT EXTRACTION (Silent)**
- Analyze the User Query to identify:
  1. **Subject Location:** (e.g., "Germany", "New York", "Remote")
  2. **Subject Role:** (e.g., "Intern", "Director", "Contractor")
  3. **Action:** (e.g., "Karaoke", "Gift giving", "Working at heights")

**STEP 2: DOCUMENT SCOPE FILTERING (CRITICAL)**
- You will be provided with multiple text chunks. For *each* chunk, you must extract its "Scope of Application" from the header or intro.
- **The Scope Test:**
  - If a document says "Applies to: APAC", and the User is in "Germany" -> **DISCARD** this document immediately. It is irrelevant.
  - If a document says "Applies to: Senior VPs", and the User is an "Intern" -> **DISCARD**.
  - If a document has NO specific scope, assume it is **GLOBAL** (Applies to everyone).

**STEP 3: HIERARCHY OF AUTHORITY (CONFLICT RESOLUTION)**
- If multiple valid documents apply to the user, but they conflict (one says "Allowed", one says "Banned"), use this Precedence Order:
  1. **Local/Regional Addendums:** (Highest Authority - Specific overrides General).
  2. **Global Mandatory Policy:** (Medium Authority).
  3. **General Guidelines/Code of Conduct:** (Lowest Authority).
- *Example:* Global Policy says "Gifts <$150 ok". Japan Addendum says "Gifts $0". User is in Japan. -> Result: **$0 Limit applies.**

**STEP 4: FINAL ADJUDICATION**
- Based *only* on the documents that passed the Scope Test and won the Hierarchy Check, determine the status.
- **DEFAULT STATE:** If no active policy explicitly forbids an action, it is PERMITTED.

### OUTPUT FORMAT (STRICT JSON):
You must output ONLY a valid JSON object. No markdown, no conversational text.
{
  "risk_level": "CRITICAL" | "HIGH" | "MODERATE" | "LOW",
  "action": "BLOCK" | "FLAG" | "APPROVE",
  "violation_summary": "Short, punchy title (Max 5 words)",
  "detailed_analysis": "A clear explanation. You MUST reference the 'Why'. E.g., 'Allowed because the APAC restrictions do not apply to Germany.' or 'Blocked due to Japan Regional Override (Section 2.1).'"
}
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
    # DEFENSIVE: Ensure text is a string
    if not isinstance(text, str):
        text = str(text) if text else ""

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


def decompose_query(question: str, llm: ChatOpenAI = None) -> List[Dict[str, any]]:
    """
    Decompose a query into multiple sub-queries if it contains multiple entities.
    SIMPLIFIED: Returns single query to avoid LLM errors.
    """
    try:
        # Detect regions in question
        region_detection = detect_regions_in_text(question)
        detected_regions = region_detection.get("regions", ["GLOBAL"])

        # CRITICAL: Only return the regions actually mentioned in the question
        # This prevents hallucination where Germany also retrieves APAC docs
        if not detected_regions:
            detected_regions = ["GLOBAL"]

        # Return a single query covering only the detected regions
        return [{
            "entity": "Query",
            "query": question,
            "regions": detected_regions
        }]
    except Exception as e:
        # Fallback to safest possible response - ONLY GLOBAL, not all regions!
        # Returning all regions would contaminate Germany queries with APAC policies
        print(f"decompose_query error: {e}")
        return [{
            "entity": "Query",
            "query": question,
            "regions": ["GLOBAL"]  # SAFE DEFAULT: Only global applies everywhere
        }]


def filter_documents_by_regions(documents: List[Document], allowed_regions: List[str]) -> List[Document]:
    """
    STRICT document filtering by region scope.

    Prevents cross-region contamination by ensuring documents are only used
    when they explicitly apply to the query's region.

    Logic:
    - Document with regions=["GLOBAL"] → Include (applies everywhere)
    - Document with regions=["APAC"] → Include ONLY if "APAC" in allowed_regions
    - Document with regions=["APAC", "GLOBAL"] → Include only if query region matches or is GLOBAL
    - Document with regions=["EMEA"] + query region=["APAC"] → EXCLUDE
    """
    if not allowed_regions:
        return documents

    filtered = []
    for doc in documents:
        doc_regions = doc.metadata.get("regions", ["GLOBAL"])

        # CRITICAL: GLOBAL documents apply everywhere
        if doc_regions == ["GLOBAL"]:
            filtered.append(doc)
            continue

        # For region-specific documents: must have strict region match
        # A document tagged ["APAC"] should only be used for APAC queries
        # A document tagged ["APAC", "GLOBAL"] is still APAC-specific, not global

        # Check if ANY doc region is in allowed regions (and not just GLOBAL)
        # This prevents APAC docs from being included in Germany queries
        has_matching_region = any(
            region in doc_regions
            for region in allowed_regions
            if region != "GLOBAL"  # Don't match on GLOBAL tag
        )

        if has_matching_region:
            filtered.append(doc)

    return filtered


def extract_metadata_from_content(content: str, chunk: str) -> Dict[str, any]:
    """
    Extract region metadata from document content with STRICT scope detection.

    KEY: If document header/title explicitly states a region scope (e.g., "APAC"),
    ALL chunks inherit that scope and are NOT tagged as GLOBAL unless explicitly stated.

    Logic:
    - If document title/header says "Regional Addendum: APAC" → regions=["APAC"]
    - If document title/header says "Global Code" → regions=["GLOBAL"]
    - If full document content mentions "Applies To: All Employees Globally" → regions=["GLOBAL"]
    - If chunk mentions APAC scope indicators → regions=["APAC"]
    """
    # DEFENSIVE: Ensure inputs are strings
    if not isinstance(chunk, str):
        chunk = str(chunk) if chunk else ""
    if not isinstance(content, str):
        content = str(content) if content else ""

    region_detection = detect_regions_in_text(chunk)

    # Check for strong scope indicators in chunk
    chunk_lower = chunk.lower()
    content_lower = content.lower()

    # CRITICAL: If chunk explicitly mentions a region scope ("Applies To: APAC", "Region: APAC"), respect it
    # Use STRICT matching to avoid false positives (e.g., "does NOT apply to Europe" shouldn't tag as EMEA)

    # Check for APAC scope (most important since it has restrictions)
    if any(phrase in chunk_lower for phrase in ["applies to: apac", "region: apac", "asia-pacific region", "apac region only", "regional addendum to global"]):
        regions = ["APAC"]
    # Check for APAC scope in full document (for chunks without explicit header)
    elif any(phrase in content_lower for phrase in ["regional addendum to global", "asia-pacific region", "apac region only"]) and "does not apply to apac" not in content_lower:
        regions = ["APAC"]
    # Check for EMEA scope (but avoid matching "does not apply to Europe")
    elif any(phrase in chunk_lower for phrase in ["applies to: emea", "region: emea"]) and "does not apply" not in chunk_lower:
        regions = ["EMEA"]
    # Check for US scope
    elif any(phrase in chunk_lower for phrase in ["applies to: us", "region: us"]) and "does not apply" not in chunk_lower:
        regions = ["US"]
    # Check for GLOBAL scope (but be careful not to match content that mentions global in other contexts)
    elif any(phrase in chunk_lower for phrase in ["applies to: all", "applies to: global", "worldwide policy", "global code", "global policy"]):
        regions = ["GLOBAL"]
    else:
        # Fallback: Check if document-level scope exists
        # This prevents chunks that don't have explicit scope from mixing regions
        if any(phrase in content_lower for phrase in ["regional addendum to global", "asia-pacific region"]):
            regions = ["APAC"]
        elif any(phrase in content_lower for phrase in ["applies to: emea", "region: emea"]):
            regions = ["EMEA"]
        else:
            # DEFAULT: Assume GLOBAL if no specific region markers found
            # This allows global policy documents to be used for all queries
            regions = ["GLOBAL"]

    return {
        "regions": regions,
        "source_length": len(chunk),
        "entities": region_detection["entities"],
        "scope_type": "regional" if regions != ["GLOBAL"] else "global"
    }


def extract_json_from_response(response_text: str) -> Dict[str, any]:
    """
    CRASH-PROOF JSON extraction from LLM response.

    Multi-layer fallback strategy:
    1. Clean markdown wrappers and try direct JSON.parse()
    2. Regex extract first { to last } and parse
    3. Fallback to safe defaults

    Always returns a valid dict, never crashes.
    """
    import json

    # DEFENSIVE: Ensure response_text is a string
    if not isinstance(response_text, str):
        response_text = str(response_text) if response_text else "{}"

    # LAYER 1: Clean markdown and try direct parse
    try:
        clean_text = response_text.replace('```json', '').replace('```', '').strip()
        parsed_json = json.loads(clean_text)
        parsed_json = _remove_hallucinations_from_json(parsed_json)
        return parsed_json
    except json.JSONDecodeError:
        pass

    # LAYER 2: Regex extract JSON object (first { to last })
    try:
        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if json_match:
            json_str = json_match.group(0)
            parsed_json = json.loads(json_str)
            parsed_json = _remove_hallucinations_from_json(parsed_json)
            return parsed_json
    except (json.JSONDecodeError, AttributeError):
        pass

    # LAYER 3: Markdown code block extraction
    try:
        json_match = re.search(r'```json\s*\n?\s*({.*?})\s*\n?```', response_text, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
            parsed_json = json.loads(json_str)
            parsed_json = _remove_hallucinations_from_json(parsed_json)
            return parsed_json
    except (json.JSONDecodeError, AttributeError):
        pass

    # LAYER 4: FAILSAFE - Return valid response with raw text
    # This prevents the server from crashing
    return {
        "risk_level": "MODERATE",
        "action": "FLAG",
        "violation_summary": "Analysis Format Error",
        "detailed_analysis": f"System analyzed documents but formatting was incorrect. Raw response: {response_text[:500]}"
    }


def _remove_hallucinations_from_json(json_obj: Dict[str, any]) -> Dict[str, any]:
    """
    Post-process JSON to remove hallucinated content from all text fields.

    Hallucination patterns to remove:
    - "including X" where X is NOT explicitly mentioned in document scope
    - "which includes X" (variant of above)
    - Geographic inference (e.g., "Germany" when document only says "APAC")
    - Inference phrases: "in particular", "such as", "notably", "for example"
    """

    # Fields to clean: both violation_summary and detailed_analysis
    fields_to_clean = ["violation_summary", "detailed_analysis"]

    for field in fields_to_clean:
        if field not in json_obj:
            continue

        text = json_obj[field]

        # CRITICAL: Ensure text is a string before regex operations
        if not isinstance(text, str):
            text = str(text) if text else ""

        # CRITICAL HALLUCINATION REMOVAL PATTERNS
        # Pattern 1: Remove ", including [Location]" constructs
        # Examples: ", including Germany" or ", including Japan"
        text = re.sub(
            r',\s*including\s+[A-Z][a-zA-Z\s,&]*(?=[\.;,\s]|$)',
            '',
            text,
            flags=re.IGNORECASE
        )

        # Pattern 2: Remove "which includes [Location]" constructs
        # Examples: "which includes Germany" or "which includes Japan"
        text = re.sub(
            r',?\s+which\s+includes?\s+[A-Z][a-zA-Z\s,&]*(?=[\.;,\s]|$)',
            '',
            text,
            flags=re.IGNORECASE
        )

        # Pattern 3: Remove standalone "including" followed by location/region name
        text = re.sub(
            r'\s+including\s+[A-Z][a-zA-Z\s,&]*(?=[\.;,\s]|$)',
            '',
            text,
            flags=re.IGNORECASE
        )

        # Pattern 4: Remove inference phrases that indicate hallucination
        inference_patterns = [
            r',?\s+in\s+particular[,\s]',  # "in particular" - inference marker
            r',?\s+such\s+as\s+',  # "such as X" - examples added beyond document
            r',?\s+for\s+example[,\s]',  # "for example X"
            r',?\s+notably[,\s]',  # "notably X" - emphasizing inferred points
            r'\s+and\s+also\s+',  # "and also" - adds extra info
        ]

        for pattern in inference_patterns:
            text = re.sub(pattern, ' ', text, flags=re.IGNORECASE)

        # Clean up multiple spaces and trim
        text = re.sub(r'\s+', ' ', text)
        text = text.strip()

        # Remove dangling commas at end
        text = re.sub(r',\s*$', '', text)

        json_obj[field] = text

    return json_obj


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

    # CRITICAL FIX: If filtering removes all docs, return ONLY GLOBAL docs, not unfiltered fallback
    # This prevents APAC policies from contaminating Germany queries
    if filtered_docs:
        return filtered_docs
    else:
        # Fallback: try to get more docs and filter them, or return GLOBAL only
        try:
            more_docs = vector_store.similarity_search(sub_query["query"], k=20)
            filtered_more = filter_documents_by_regions(more_docs, sub_query["regions"])
            return filtered_more if filtered_more else []
        except:
            return []


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

    # Extract user locations from sub_queries
    user_locations = set()
    for sub_query in sub_queries:
        if "entity" in sub_query:
            user_locations.add(sub_query["entity"])

    # Build context for each region separately
    region_contexts = {}
    for entity, docs in retrieval_results.items():
        if docs:
            context = "\n\n".join([doc.page_content for doc in docs])
            region_contexts[entity] = context

    if not region_contexts:
        return "No relevant policies found in the knowledge base."

    # Create an extraction prompt (not synthesis)
    # IMPORTANT: Include user location explicitly to prevent hallucination
    user_location_str = " and ".join(sorted(user_locations)) if user_locations else "unknown"

    extraction_prompt = f"""{RISK_OFFICER_PROMPT}

USER LOCATION: {user_location_str}
ORIGINAL QUESTION: {question}

CRITICAL REMINDER:
You are analyzing policies for [{user_location_str}] ONLY.
Do NOT apply policies from other regions.
Do NOT say "including {user_location_str}" unless {user_location_str} is EXPLICITLY listed in the document scope.

RETRIEVED POLICY DOCUMENTS:
"""

    for entity, context in region_contexts.items():
        extraction_prompt += f"\n[DOCUMENT - {entity.upper()}]:\n{context}\n"

    extraction_prompt += f"""
EXTRACTION TASK:
You are in EXTRACTION MODE. Do NOT synthesize or provide recommendations.

IMPORTANT: This query involves multiple locations: {user_location_str}
For EACH location, provide a SEPARATE assessment in the detailed_analysis.

Your task:
1. For EACH location in [{user_location_str}]:
   a. Find the explicit scope statement in each document
   b. Check if [LOCATION] is EXPLICITLY mentioned in that scope
      - Explicit = directly named or listed in parentheses
      - NOT explicit = regional classification like "APAC" without listing [LOCATION]
   c. If YES: Extract what policies apply to [LOCATION]
   d. If NO: State that document does not apply to [LOCATION]

2. Build separate policy assessment for each location in detailed_analysis

CRITICAL CONSTRAINTS:
- Provide analysis for ALL locations mentioned: {user_location_str}
- Do NOT say "including [LOCATION]" unless it's in the document
- Do NOT infer that [LOCATION] is in a region unless explicit
- Do NOT use contextual knowledge about geography
- For each location: clearly state whether policies APPLY or DO NOT APPLY
- If document says "APAC region" but doesn't list a location, then that document does NOT apply to that location

Do NOT combine information from multiple documents.
Do NOT infer document scope beyond what is explicitly stated.
Do NOT add contextual knowledge.

OUTPUT FORMAT FOR MULTIPLE LOCATIONS:
If analyzing multiple locations, structure detailed_analysis as:

[LOCATION 1]:
- Policy 1 applies/does not apply because...
- Policy 2 applies/does not apply because...
- Overall risk: [reason]

[LOCATION 2]:
- Policy 1 applies/does not apply because...
- Policy 2 applies/does not apply because...
- Overall risk: [reason]

Return ONLY the JSON object with extracted facts."""

    response = llm.invoke(extraction_prompt)
    # DEFENSIVE: Ensure response is a string
    result = response.content if hasattr(response, 'content') else str(response)
    if not isinstance(result, str):
        result = str(result) if result else ""
    return result


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

        documents = []
        files_processed = 0
        all_regions = set()

        # CRITICAL FIX: Process each PDF file separately
        # This prevents metadata from one document contaminating another
        for file in files:
            if not file.filename.endswith('.pdf'):
                continue

            # Read PDF content
            file_text = ""
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
                content = await file.read()
                tmp.write(content)
                tmp.flush()

                # Parse PDF
                pdf_reader = PdfReader(tmp.name)
                for page in pdf_reader.pages:
                    file_text += page.extract_text() + "\n"

                files_processed += 1

            # Clean up temp file
            os.unlink(tmp.name)

            if not file_text:
                continue

            # Split THIS FILE's text into chunks (not combined with other files)
            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=1000,
                chunk_overlap=200,
                separators=["\n\n", "\n", " ", ""]
            )
            file_chunks = text_splitter.split_text(file_text)

            # Create documents with metadata for each chunk
            # CRITICAL: Pass file_text (single document), NOT combined text of all files
            for chunk in file_chunks:
                metadata = extract_metadata_from_content(file_text, chunk)
                all_regions.update(metadata["regions"])

                # Create LangChain Document with metadata
                doc = Document(
                    page_content=chunk,
                    metadata=metadata
                )
                documents.append(doc)

        if not documents:
            raise HTTPException(
                status_code=400,
                detail="No text chunks created from PDFs"
            )

        # Create embeddings and vector store with metadata
        embeddings = OpenAIEmbeddings(
            model="text-embedding-ada-002",
            openai_api_key=os.getenv("OPENAI_API_KEY")
        )

        vector_store = FAISS.from_documents(documents, embeddings)
        all_documents = documents

        return {
            "status": "success",
            "chunks": len(documents),
            "files_processed": files_processed,
            "regions_detected": list(all_regions),
            "message": f"Successfully processed {files_processed} PDF file(s) into {len(documents)} chunks with metadata routing"
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
        try:
            sub_queries = decompose_query(question, llm)
        except Exception as decompose_error:
            print(f"Query decomposition error: {decompose_error}")
            # Fallback: treat whole question as single query
            sub_queries = [{
                "entity": "general",
                "query": question,
                "regions": ["GLOBAL", "APAC", "EMEA", "US"]
            }]

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
        try:
            answer = synthesize_comparative_answer(
                question,
                sub_queries,
                retrieval_results,
                llm
            )
        except Exception as synthesis_error:
            print(f"Synthesis error: {synthesis_error}")
            answer = '{"risk_level":"MODERATE","action":"FLAG","violation_summary":"Analysis in progress","detailed_analysis":"System encountered an error during synthesis"}'

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
        try:
            json_classification = extract_json_from_response(answer)
        except Exception as extract_error:
            # Fallback if extraction fails
            print(f"JSON extraction error: {extract_error}")
            json_classification = {
                "risk_level": "MODERATE",
                "action": "FLAG",
                "violation_summary": "Analysis interpretation required",
                "detailed_analysis": answer
            }

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
        # CRASH-PROOF: Return a safe response instead of 500 error
        import traceback
        error_trace = traceback.format_exc()
        print(f"ERROR in /query: {error_trace}")

        # Return valid compliance response even on error
        return {
            "answer": f"System encountered an error processing your query: {str(e)}",
            "sources": [],
            "compliance_status": "REQUIRES REVIEW",
            "documents_searched": 0,
            "query_decomposition": [],
            "regions_analyzed": [],
            "decomposition_note": "Error during analysis",
            "violation_summary": "System Error",
            "risk_classification": {
                "risk_level": "MODERATE",
                "action": "FLAG",
                "violation_summary": "Processing Error",
                "detailed_analysis": f"The compliance system encountered an error: {str(e)}"
            }
        }


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
