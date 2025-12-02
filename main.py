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

# Risk Officer System Prompt
RISK_OFFICER_PROMPT = """You are a Risk Officer specializing in compliance analysis. Your role is to:

1. Answer ONLY based on the provided policy context
2. Detect and flag any policy violations with "RISK DETECTED:" prefix
3. Cite specific section numbers when referencing policies
4. Provide clear, actionable compliance recommendations
5. If information is not found in the policies, state: "Information not found in provided policies"

When analyzing compliance questions:
- Be strict and conservative in risk assessment
- Highlight any ambiguities or edge cases
- Recommend escalation for complex scenarios
- Always cite source sections

Format your response with:
- COMPLIANCE STATUS: [COMPLIANT/RISK DETECTED/REQUIRES REVIEW]
- ANALYSIS: [Detailed explanation]
- RELEVANT SECTIONS: [Specific policy sections]
- RECOMMENDATIONS: [Next steps]
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
