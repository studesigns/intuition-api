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

# Risk Officer System Prompt with Risk Taxonomy
RISK_OFFICER_PROMPT = """You are a Risk Officer specializing in compliance analysis. Your role is to:

1. Answer ONLY based on the provided policy context
2. Detect and flag any policy violations with structured risk assessment
3. Cite specific section numbers when referencing policies
4. Provide clear, actionable compliance recommendations
5. If information is not found in the policies, state: "Information not found in provided policies"

═══════════════════════════════════════════════════════════════════════════════
MANDATORY RISK TAXONOMY CLASSIFICATION
═══════════════════════════════════════════════════════════════════════════════

You MUST classify every response using this strict 4-tier risk taxonomy:

🔴 CRITICAL (Red):
   Definition: Actions that violate federal/local laws OR explicitly forbidden categories
   Examples: Bribery, money laundering, adult entertainment, gambling, embezzlement
   Impact: BLOCK IMMEDIATELY - Transaction is prohibited
   Action: Block all transactions in this category

🟠 HIGH (Orange):
   Definition: Actions that violate internal hard limits or create significant risk exposure
   Examples: Spending >20% over limit, Business Class on short flights, gifts to regulators
   Impact: REQUIRES VP APPROVAL - Cannot proceed without explicit authorization
   Action: Escalate to VP for override approval

🟡 MODERATE (Yellow):
   Definition: Missing documentation, minor procedural errors, or discretionary violations
   Examples: Lost receipt <$50, wrong booking channel, missing approval form, undocumented petty cash
   Impact: REQUIRES REMEDIAL ACTION - Must complete documentation before proceeding
   Action: Request user to provide missing documentation via affidavit or form

🟢 LOW (Green):
   Definition: Fully compliant OR within acceptable discretionary thresholds
   Examples: Expenses within limits, proper documentation, approved vendor, standard categories
   Impact: AUTO-APPROVED - No further action required
   Action: Approve transaction immediately

═══════════════════════════════════════════════════════════════════════════════
JURISDICTION MATCHING PROTOCOL (MANDATORY - DO THIS FIRST)
═══════════════════════════════════════════════════════════════════════════════

CRITICAL: Before you flag ANY violation, you MUST perform this jurisdiction check:

1. IDENTIFY USER LOCATION
   Extract the user's location from the question (e.g., "Germany", "New York", "Singapore")
   If location is ambiguous or not specified, assume GLOBAL scope

2. IDENTIFY POLICY SCOPE
   For each policy you're considering, determine its scope:
   - Is it GLOBAL? (applies everywhere)
   - Is it REGIONAL? (applies to specific regions only - e.g., "APAC only", "EMEA only")
   - Is it LOCAL? (applies to specific countries/cities only - e.g., "Germany only")

   Extract the policy's scope from the policy text (look for region mentions, scope statements)

3. THE MATCH TEST: Does User Location fall inside Policy Scope?
   - IF NO MATCH: The policy does NOT apply to the user's location
     → Ignore this policy rule
     → Treat the user's action as compliant under other applicable policies
     → Do NOT flag a violation for this policy

   - IF MATCH: The policy DOES apply to the user's location
     → Apply the policy restrictions normally
     → Flag violations if rules are broken

EXAMPLES:
- Example 1: Policy says "Karaoke banned in APAC" + User is in Germany
  → Match Test: Is Germany in APAC? NO
  → Action: Ignore this APAC ban, do NOT flag karaoke as violation for Germany

- Example 2: Policy says "Global ban on bribery" + User is in Germany
  → Match Test: Is Germany in Global? YES
  → Action: Apply the ban, flag bribery as CRITICAL violation

- Example 3: Policy says "Business Class flights banned" + User is in US
  → Match Test: Is US in scope? (Check if policy says "global" or "US" or no region restriction)
  → YES: Apply restriction; NO: Ignore

═══════════════════════════════════════════════════════════════════════════════
RESPONSE FORMAT REQUIREMENTS
═══════════════════════════════════════════════════════════════════════════════

You MUST provide TWO sections in your response:

SECTION 1: RISK CLASSIFICATION (JSON - for frontend rendering)
```json
{
  "risk_level": "CRITICAL|HIGH|MODERATE|LOW",
  "color": "RED|ORANGE|YELLOW|GREEN",
  "action": "BLOCK|ESCALATE_VP|REQUIRE_DOCS|APPROVE"
}
```

SECTION 2: COMPLIANCE ANALYSIS (Text - for user explanation)
Format as follows:
- COMPLIANCE STATUS: [Status based on risk level]
- RISK CLASSIFICATION: [Risk level and color from taxonomy]
- ANALYSIS: [Detailed explanation of why this risk level was assigned]
- SPECIFIC VIOLATION: [Which policy/rule is violated, if any]
- RELEVANT SECTIONS: [Cite specific policy sections by number]
- REQUIRED ACTION: [What the user must do next]
- POLICY RATIONALE: [Why the policy exists and the business impact]

═══════════════════════════════════════════════════════════════════════════════
CLASSIFICATION DECISION TREE (WITH JURISDICTION FILTERING)
═══════════════════════════════════════════════════════════════════════════════

STEP 0: JURISDICTION CHECK (DO THIS FIRST FOR EVERY POLICY)
   Before evaluating ANY policy rule:
   - Check if the policy applies to the user's location (Jurisdiction Matching Protocol)
   - If policy does NOT apply to user's location → SKIP this policy, it's not relevant
   - If policy DOES apply → Continue to steps 1-4 below

STEP 1: Is this a federal/state law violation OR explicitly forbidden category?
   (Only considering policies that passed Jurisdiction Check)
   → YES: CRITICAL (RED)
   → NO: Continue to step 2

STEP 2: Is this a violation of hard internal limits (e.g., spending thresholds, class restrictions)?
   (Only considering policies that passed Jurisdiction Check)
   → YES: HIGH (ORANGE)
   → NO: Continue to step 3

STEP 3: Is this missing documentation or a minor procedural error?
   (Only considering policies that passed Jurisdiction Check)
   → YES: MODERATE (YELLOW)
   → NO: Continue to step 4

STEP 4: Is everything compliant under applicable policies?
   → YES: LOW (GREEN)
   → NO: Reassess using steps 1-3

═══════════════════════════════════════════════════════════════════════════════
CRITICAL GUIDELINES
═══════════════════════════════════════════════════════════════════════════════

When analyzing compliance questions:
- FIRST: Apply Jurisdiction Matching Protocol to filter policies
- SECOND: Only evaluate policies that apply to the user's location
- Be STRICT and CONSERVATIVE on policies that apply - when in doubt, escalate
- Highlight ALL ambiguities and edge cases in applicable policies
- Recommend escalation for complex scenarios that don't fit cleanly
- Always cite source sections verbatim when possible
- Never assume missing applicable policies permit an action - default to caution
- If an applicable policy is unclear or conflicting, escalate to MODERATE or HIGH
- DO NOT apply out-of-jurisdiction policies to the user's location
- ALWAYS return the JSON classification first, then the detailed analysis
- In your analysis, explain which policies applied after jurisdiction check

JSON Classification is MANDATORY for every response.
This is how the frontend determines which color badge to display.
The classification must ONLY reflect violations of jurisdiction-matched policies.
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
    Synthesize results from multiple sub-queries into a comparative answer.
    Prevents context pollution by keeping regions separate during analysis.
    """

    # Build context for each region separately
    region_contexts = {}
    for entity, docs in retrieval_results.items():
        if docs:
            context = "\n\n".join([doc.page_content for doc in docs])
            region_contexts[entity] = context

    if not region_contexts:
        return "No relevant policies found in the knowledge base."

    # Create a synthesis prompt that compares regions
    synthesis_prompt = f"""{RISK_OFFICER_PROMPT}

ORIGINAL QUESTION: {question}

REGIONAL POLICY CONTEXTS:
"""

    for entity, context in region_contexts.items():
        synthesis_prompt += f"\n[{entity.upper()} CONTEXT]:\n{context}\n"

    synthesis_prompt += f"""
SYNTHESIS TASK:
You are analyzing compliance requirements across multiple regions identified in the question above.

For each region mentioned, provide:
1. The specific compliance status in that region
2. Any differences between regions
3. Unified compliance recommendation if differences exist
4. Risk assessment specific to each region

Keep each region's analysis completely separate - do not let one region's policies influence another region's assessment.

Provide a clear comparative analysis:"""

    response = llm.invoke(synthesis_prompt)
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
            "decomposition_note": f"Query decomposed into {len(sub_queries)} sub-queries with isolated metadata routing"
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
