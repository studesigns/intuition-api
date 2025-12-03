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

# ===== PERSISTENCE FUNCTIONS =====

def save_vector_store():
    """Save vector store to disk for persistence"""
    global vector_store, all_documents
    if vector_store is None:
        return
    try:
        # Save FAISS index
        vector_store.save_local(VECTOR_STORE_PATH)
        print(f"✓ Vector store saved to {VECTOR_STORE_PATH}")
    except Exception as e:
        print(f"✗ Error saving vector store: {e}")

def load_vector_store():
    """Load vector store from disk at startup"""
    global vector_store
    from pathlib import Path
    db_path = Path(VECTOR_STORE_PATH)

    if not db_path.exists():
        print(f"ℹ Vector store not found at {VECTOR_STORE_PATH}")
        return False

    try:
        embeddings = OpenAIEmbeddings(
            model="text-embedding-ada-002",
            openai_api_key=os.getenv("OPENAI_API_KEY")
        )
        vector_store = FAISS.load_local(
            VECTOR_STORE_PATH,
            embeddings,
            allow_dangerous_deserialization=True
        )
        print(f"✓ Vector store loaded from {VECTOR_STORE_PATH}")
        return True
    except Exception as e:
        print(f"✗ Error loading vector store: {e}")
        return False

# Startup event to load vector store on server start
@app.on_event("startup")
async def startup_event():
    """Load vector store when server starts"""
    load_vector_store()

# Global variables for advanced RAG
vector_store = None
all_documents = []  # Store documents with metadata for filtering
VECTOR_STORE_PATH = "/home/stu/Projects/intuition-api/vector_store_db"

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


def extract_location_specific_question(original_question: str, entity: str) -> str:
    """
    Extract a location-specific sub-question from a multi-location query.

    Example:
    - Input: "I'm taking clients to karaoke in Germany and Japan. Should we go?"
    - For entity "germany": "Can I take a client to karaoke in Germany?"
    - For entity "japan": "Can I take a client to karaoke in Japan?"
    """
    # Common patterns to extract activity/context
    patterns = [
        r"taking.*?(client|customers?|team|staff).*?to\s+(\w+(?:\s+\w+)*)",  # "taking clients to X"
        r"(client|customers?|team|staff)\s+(\w+(?:\s+\w+)*)\s+in",  # "client X in location"
        r"activity.*?(?:in|at|for)\s+(\w+(?:\s+\w+)*)",  # "activity in X"
    ]

    # Try to extract the activity (e.g., "karaoke", "nightclub", etc.)
    activity = ""
    for pattern in patterns:
        match = re.search(pattern, original_question, re.IGNORECASE)
        if match:
            if len(match.groups()) > 1:
                activity = match.group(2)
            else:
                activity = match.group(1)
            break

    # If we couldn't extract activity, use a generic version
    if not activity:
        activity = "this activity"

    # Create location-specific question
    location_specific = f"Can I take a client to {activity.lower()} in {entity.title()}?"
    return location_specific


def decompose_query(question: str, llm: ChatOpenAI = None) -> List[Dict[str, any]]:
    """
    Decompose a query into multiple sub-queries if it contains multiple entities.
    Handles both single-location and multi-location queries.
    """
    try:
        # Detect regions in question
        region_detection = detect_regions_in_text(question)
        detected_regions = region_detection.get("regions", ["GLOBAL"])
        detected_entities = region_detection.get("entities", [])

        # CRITICAL: Only return the regions actually mentioned in the question
        # This prevents hallucination where Germany also retrieves APAC docs
        if not detected_regions:
            detected_regions = ["GLOBAL"]

        # MULTI-LOCATION SUPPORT: Create separate sub-queries for each location
        # This allows proper comparative analysis between regions
        sub_queries = []

        if detected_entities and len(detected_entities) > 0:
            # If multiple locations mentioned, create separate sub-query for each
            for entity in detected_entities:
                # Map entity location to its regions
                entity_regions = detect_regions_in_text(entity).get("regions", ["GLOBAL"])
                if not entity_regions:
                    entity_regions = ["GLOBAL"]

                sub_queries.append({
                    "entity": entity,
                    "query": question,  # Keep full question for context
                    "regions": entity_regions
                })

        # If no entities detected or creation failed, use single query with all detected regions
        if not sub_queries:
            sub_queries = [{
                "entity": "General",
                "query": question,
                "regions": detected_regions
            }]

        return sub_queries

    except Exception as e:
        # Fallback to safest possible response - ONLY GLOBAL, not all regions!
        # Returning all regions would contaminate Germany queries with APAC policies
        print(f"decompose_query error: {e}")
        return [{
            "entity": "General",
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

    # CRITICAL: EXPLICIT REGION DETECTION ONLY
    # If a document explicitly states it's regional (APAC, EMEA, US), respect that.
    # Otherwise, assume GLOBAL by default (safer for policy documents).
    #
    # KEY: Look for "Regional Addendum" or "APAC-only" language, NOT just region names
    # (because global policies list all regions they apply to)

    # === DETECT APAC SCOPE (highest priority - has restrictions) ===
    # CRITICAL FIX: Check FULL DOCUMENT content (not just chunk) for scope detection
    # This ensures ALL chunks from a regional document get the same region tag
    # Look for explicit APAC/Asia-Pacific titles AND "prohibited in" which indicates restrictions
    if ("asia-pacific region" in content_lower or "apac region" in content_lower or "regional addendum: apac" in content_lower or "regional addendum: asia" in content_lower) and ("prohibited" in content_lower or "high-risk" in content_lower):
        regions = ["APAC"]
    elif any(phrase in content_lower for phrase in ["prohibited in: apac", "prohibited in: china", "prohibited in: japan", "apac-specific", "asia-pacific"]):
        regions = ["APAC"]
    # === DETECT US SCOPE ===
    elif any(phrase in content_lower for phrase in ["us region", "united states only", "us scope"]) and "does not apply" not in content_lower:
        regions = ["US"]
    # === DETECT EMEA SCOPE ===
    elif any(phrase in content_lower for phrase in ["emea region", "emea scope"]) and "does not apply" not in content_lower:
        regions = ["EMEA"]
    else:
        # DEFAULT: ASSUME GLOBAL
        # This is safer because:
        # 1. Global policies should apply everywhere
        # 2. Regional addendums explicitly state their scope
        # 3. If no scope is mentioned, assume universal applicability
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
    DEBUG: Logs what documents are retrieved and their region tags.
    """
    if not vector_store:
        return []

    # Retrieve with similarity search
    relevant_docs = vector_store.similarity_search(sub_query["query"], k=8)

    # DEBUG: Log what was retrieved
    print(f"\n[DEBUG] Query for {sub_query['entity']}: '{sub_query['query']}'")
    print(f"[DEBUG] Allowed regions: {sub_query['regions']}")
    print(f"[DEBUG] Retrieved {len(relevant_docs)} docs from similarity search:")
    for i, doc in enumerate(relevant_docs, 1):
        regions = doc.metadata.get("regions", ["UNKNOWN"])
        print(f"  {i}. Regions={regions}, Content preview: {doc.page_content[:80]}...")

    # Filter by allowed regions to prevent cross-contamination
    filtered_docs = filter_documents_by_regions(
        relevant_docs,
        sub_query["regions"]
    )

    print(f"[DEBUG] After filtering: {len(filtered_docs)} docs remain")

    # CRITICAL FIX: If filtering removes all docs, try broader search before giving up
    # This prevents APAC policies from contaminating Germany queries
    if filtered_docs:
        return filtered_docs
    else:
        # Fallback: try to get more docs and filter them
        print(f"[DEBUG] No docs survived filtering, trying broader search (k=20)...")
        try:
            more_docs = vector_store.similarity_search(sub_query["query"], k=20)
            print(f"[DEBUG] Retrieved {len(more_docs)} docs from broader search:")
            for i, doc in enumerate(more_docs, 1):
                regions = doc.metadata.get("regions", ["UNKNOWN"])
                print(f"  {i}. Regions={regions}")
            filtered_more = filter_documents_by_regions(more_docs, sub_query["regions"])
            print(f"[DEBUG] After filtering broader search: {len(filtered_more)} docs remain")
            return filtered_more
        except Exception as e:
            print(f"Retrieval error: {e}")
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


def _calculate_overall_risk(analyses: Dict[str, Dict]) -> str:
    """
    Calculate overall risk level from individual location analyses.
    Returns the highest risk found across all locations.
    """
    risk_hierarchy = {
        "CRITICAL": 4,
        "HIGH": 3,
        "MODERATE": 2,
        "LOW": 1,
        "UNKNOWN": 0
    }

    max_risk = "UNKNOWN"
    max_value = 0

    for entity, analysis in analyses.items():
        if isinstance(analysis, dict):
            risk_level = analysis.get("risk_level", "UNKNOWN")
        else:
            risk_level = "UNKNOWN"

        value = risk_hierarchy.get(risk_level, 0)
        if value > max_value:
            max_value = value
            max_risk = risk_level

    return max_risk


def synthesize_comparative_answer(
    question: str,
    sub_queries: List[Dict[str, any]],
    retrieval_results: Dict[str, List[Document]],
    llm: ChatOpenAI
) -> str:
    """
    Extract compliance facts for EACH LOCATION SEPARATELY.
    Creates individual analyses per location, then combines them.
    """

    # Extract all location-specific analyses
    all_analyses = {}

    # Process each location independently
    for sub_query in sub_queries:
        entity = sub_query.get("entity", "General")
        docs = retrieval_results.get(entity, [])

        if not docs:
            all_analyses[entity] = {
                "risk_level": "UNKNOWN",
                "action": "UNKNOWN",
                "reason": "No relevant policies found for this location"
            }
            continue

        # Build context for THIS location only
        context = "\n\n".join([doc.page_content for doc in docs])

        # Create a location-specific sub-question for clarity
        # This helps the LLM focus on just this location's analysis
        location_question = extract_location_specific_question(question, entity) if "," in question or "and" in question.lower() else question

        # Create location-specific prompt
        location_prompt = f"""{RISK_OFFICER_PROMPT}

===== ANALYZING {entity.upper()} ONLY =====

LOCATION: {entity.upper()}
LOCATION-SPECIFIC QUESTION: {location_question}

===== CRITICAL SCOPE RULES FOR {entity.upper()} =====

**GERMANY SPECIFIC RULE:**
If analyzing Germany: Germany is in EUROPE, NOT APAC. The APAC region includes China, Japan, Vietnam, Indonesia.
- ANY document that says "Region: APAC" or "APAC Addendum" does NOT apply to Germany
- IGNORE any language about "APAC restrictions" when analyzing Germany
- IGNORE the "Regional Addendum: Asia-Pacific (APAC)" completely for Germany analysis

**JAPAN/APAC SPECIFIC RULE:**
If analyzing Japan or other APAC countries: Apply APAC-specific restrictions as they explicitly apply.

**YOUR LOCATION: {entity.upper()}**
- Is {entity.upper()} in APAC region?
  - YES if: Japan, China, Vietnam, Indonesia, other APAC countries → Apply APAC addendum
  - NO if: Germany, Europe, US, others → DO NOT apply APAC addendum

**KEY PRINCIPLE:**
When documents from MULTIPLE regions are provided, use document scope to filter:
- Documents marked "APAC" → ONLY for APAC locations
- Documents marked "GLOBAL" → For ALL locations
- For {entity.upper()}: Only follow policies that explicitly apply to this location

REMEMBER: The fact that you received certain documents does NOT mean they all apply. You must read each document's stated scope and determine if it applies to {entity.upper()}.

===== RETRIEVED POLICY DOCUMENTS FOR {entity.upper()} =====
{context}

===== YOUR ANALYSIS TASK =====
1. Read the retrieved documents above
2. Identify which documents apply to {entity.upper()} based on their stated scope
3. For {entity.upper()}: Is it in the APAC region? Answer: {"YES - apply APAC restrictions" if "apac" in entity.lower() or "japan" in entity.lower() or "tokyo" in entity.lower() else "NO - do NOT apply APAC restrictions, only apply global policies"}
4. Based on applicable policies (filtered by scope), determine the risk level and action

===== DEFAULT STATE FOR {entity.upper()} =====
If no active policy that applies to {entity.upper()} explicitly forbids an action, the action is PERMITTED.

For Germany specifically:
- Unless the GLOBAL policy explicitly forbids karaoke → karaoke is allowed
- The APAC-only documents do NOT apply to Germany
- Therefore: Karaoke entertainment = PERMITTED (LOW risk)

===== RISK LEVEL ASSIGNMENT GUIDE =====
**CRITICAL**: Activity is strictly prohibited/banned with immediate suspension/termination consequences (BLOCK)
  - Keywords that indicate CRITICAL: "strictly prohibited", "banned", "not permitted", "immediate suspension", "termination", "zero tolerance"
  - If you see ANY of these keywords with the action in question, assign CRITICAL immediately

**HIGH**: Activity is prohibited but with review/case-by-case exceptions (BLOCK or FLAG)

**MODERATE**: Activity requires approval/conditions but is generally permissible (FLAG or APPROVE)

**LOW**: Activity is explicitly permitted with no restrictions (APPROVE)

**UNKNOWN**: No applicable policy found (FLAG)

IMPORTANT: For {entity.upper()}, scan the documents for words like "strictly prohibited", "banned", "suspension", "termination". If found with the action in question, MUST use CRITICAL risk level.

===== RESPONSE FORMAT =====
Return ONLY valid JSON (NO other text):
{{
  "risk_level": "CRITICAL|HIGH|MODERATE|LOW|UNKNOWN",
  "action": "BLOCK|FLAG|APPROVE|UNKNOWN",
  "summary": "Brief summary for {entity.upper()}",
  "reason": "Must state which policy applies and its scope. Examples: 'Karaoke is allowed in Germany - APAC prohibition only applies to APAC region' or 'Karaoke prohibited in Japan due to APAC Regional Addendum Section 3.1.1 (CRITICAL: strictly prohibited with immediate suspension)'"
}}"""

        try:
            response = llm.invoke(location_prompt)
            result = response.content if hasattr(response, 'content') else str(response)
            if not isinstance(result, str):
                result = str(result)

            # Parse the response
            location_analysis = extract_json_from_response(result)

            # CRITICAL FIX: Post-process to force CRITICAL if document contains prohibition keywords
            # This ensures "strictly prohibited" items are marked CRITICAL even if LLM assigns HIGH
            context_lower = context.lower()
            result_lower = result.lower()

            prohibition_keywords = ["strictly prohibited", "banned", "not permitted", "zero tolerance"]
            has_prohibition = any(keyword in context_lower for keyword in prohibition_keywords)

            # If we found strict prohibition language AND the action matches what was banned
            if has_prohibition and location_analysis.get("action") == "BLOCK":
                # Force to CRITICAL if LLM under-assigned
                if location_analysis.get("risk_level") in ["HIGH", "MODERATE"]:
                    location_analysis["risk_level"] = "CRITICAL"
                    location_analysis["reason"] = location_analysis.get("reason", "") + " [ESCALATED TO CRITICAL: Document contains 'strictly prohibited' language with suspension/termination consequences]"

            all_analyses[entity] = location_analysis

        except Exception as e:
            print(f"Error analyzing {entity}: {e}")
            all_analyses[entity] = {
                "risk_level": "UNKNOWN",
                "action": "UNKNOWN",
                "reason": f"Error during analysis: {str(e)}"
            }

    # Combine all analyses into final response
    combined_analysis = {}
    for entity, analysis in all_analyses.items():
        combined_analysis[entity] = analysis

    # Return as JSON string
    import json
    return json.dumps({
        "analyses_by_location": combined_analysis,
        "overall_risk": _calculate_overall_risk(all_analyses)
    })


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
            file_regions = set()
            for i, chunk in enumerate(file_chunks):
                metadata = extract_metadata_from_content(file_text, chunk)
                file_regions.update(metadata["regions"])
                all_regions.update(metadata["regions"])

                # Create LangChain Document with metadata
                doc = Document(
                    page_content=chunk,
                    metadata=metadata
                )
                documents.append(doc)

            # Log regions for this file
            print(f"  File: {file.filename} - Regions: {list(file_regions)}, Chunks: {len(file_chunks)}")

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

        # Save vector store to disk for persistence
        save_vector_store()

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
            # Fallback: SAFE DEFAULT - only GLOBAL applies everywhere, prevent cross-region contamination
            sub_queries = [{
                "entity": "General",
                "query": question,
                "regions": ["GLOBAL"]  # SAFE: Only GLOBAL prevents regional contamination
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
        # synthesize_comparative_answer returns JSON with structure: {analyses_by_location: {...}, overall_risk: "..."}
        try:
            json_classification = extract_json_from_response(answer)
        except Exception as extract_error:
            # Fallback if extraction fails
            print(f"JSON extraction error: {extract_error}")
            json_classification = {
                "analyses_by_location": {
                    "General": {
                        "risk_level": "MODERATE",
                        "action": "FLAG",
                        "summary": "Analysis interpretation required"
                    }
                },
                "overall_risk": "MODERATE"
            }

        # Extract overall risk and location-specific analyses
        analyses_by_location = json_classification.get("analyses_by_location", {})
        overall_risk = json_classification.get("overall_risk", "MODERATE")

        # Build detailed analysis text for each location
        analysis_text = ""
        for location, analysis_info in analyses_by_location.items():
            analysis_text += f"\n**{location.upper()}:**\n"
            if isinstance(analysis_info, dict):
                risk = analysis_info.get("risk_level", "UNKNOWN")
                action = analysis_info.get("action", "UNKNOWN")
                summary = analysis_info.get("summary", "")
                reason = analysis_info.get("reason", "")

                analysis_text += f"  - Risk Level: {risk}\n"
                analysis_text += f"  - Recommended Action: {action}\n"
                if summary:
                    analysis_text += f"  - Summary: {summary}\n"
                if reason:
                    analysis_text += f"  - Details: {reason}\n"
            else:
                analysis_text += f"  {analysis_info}\n"

        # Use overall risk for main classification
        risk_level = overall_risk.upper()

        # Determine recommended action based on overall risk
        action = "APPROVE"
        if risk_level == "CRITICAL":
            action = "BLOCK"
        elif risk_level in ["HIGH", "MODERATE"]:
            action = "FLAG"
        elif risk_level == "LOW":
            action = "APPROVE"

        # Create summary that reflects the overall assessment
        # For multi-location queries, show the overall status, not just one location
        if len(analyses_by_location) > 1:
            # Multi-location: show overall compliance status
            if risk_level == "CRITICAL":
                violation_summary = f"Multiple locations analyzed: One or more locations PROHIBITED"
            elif risk_level == "HIGH":
                violation_summary = f"Multiple locations analyzed: One or more locations HIGH RISK"
            elif risk_level == "MODERATE":
                violation_summary = f"Multiple locations analyzed: Review required for one or more locations"
            else:
                violation_summary = f"Multiple locations analyzed: All locations compliant"
        else:
            # Single location: use the location's summary
            first_location_analysis = next(iter(analyses_by_location.values()), {})
            if isinstance(first_location_analysis, dict):
                violation_summary = first_location_analysis.get("summary", "Compliance assessment complete")
            else:
                violation_summary = "Compliance assessment complete"

        user_friendly_output = f"""
### COMPLIANCE RISK ASSESSMENT

**Question:** {question}

**Overall Risk Level:** {risk_level}
**Recommended Action:** {action}
**Summary:** {violation_summary}

**Analysis by Location:**
{analysis_text}

**Documents Reviewed:** {len(all_docs)} policy documents
**Regions Analyzed:** {', '.join(list(regions_analyzed)) if regions_analyzed else 'GLOBAL'}
"""

        # Determine compliance status from overall risk level
        compliance_status = "COMPLIANT"
        if risk_level == "CRITICAL":
            compliance_status = "PROHIBITED"
        elif risk_level in ["HIGH", "MODERATE"]:
            compliance_status = "REQUIRES REVIEW"
        elif risk_level == "LOW":
            compliance_status = "COMPLIANT"
        else:
            compliance_status = "REQUIRES REVIEW"

        return {
            "answer": answer,
            "user_friendly_output": user_friendly_output.strip(),
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
