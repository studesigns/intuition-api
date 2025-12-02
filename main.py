import os
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List
import tempfile

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain.chains.qa_with_sources import load_qa_with_sources_chain
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

# Global variable to store the vector store
vector_store = None

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
    Upload PDF policy documents to build the knowledge base.

    Args:
        files: List of PDF files to upload

    Returns:
        {
            "status": "success",
            "chunks": number of text chunks created,
            "files_processed": number of files processed
        }
    """
    global vector_store

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

        # Create embeddings and vector store
        embeddings = OpenAIEmbeddings(
            model="text-embedding-ada-002",
            openai_api_key=os.getenv("OPENAI_API_KEY")
        )

        vector_store = FAISS.from_texts(chunks, embeddings)

        return {
            "status": "success",
            "chunks": len(chunks),
            "files_processed": files_processed,
            "message": f"Successfully processed {files_processed} PDF file(s) into {len(chunks)} chunks"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing files: {str(e)}")


@app.post("/query")
async def query_policies(request: dict):
    """
    Query the compliance policies with a question.

    Args:
        request: JSON body with "question" key

    Returns:
        {
            "answer": "Risk Officer's analysis",
            "sources": ["relevant policy sections"],
            "compliance_status": "COMPLIANT|RISK DETECTED|REQUIRES REVIEW"
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

        # Similarity search
        docs = vector_store.similarity_search(question, k=5)

        if not docs:
            return {
                "answer": "No relevant policies found in the knowledge base",
                "sources": [],
                "compliance_status": "REQUIRES REVIEW"
            }

        # Initialize ChatOpenAI with Risk Officer system prompt
        llm = ChatOpenAI(
            model="gpt-3.5-turbo",
            temperature=0,  # Deterministic for compliance
            openai_api_key=os.getenv("OPENAI_API_KEY")
        )

        # Build the context from retrieved documents
        context = "\n\n".join([doc.page_content for doc in docs])

        # Create the prompt
        prompt_text = f"""{RISK_OFFICER_PROMPT}

POLICY CONTEXT:
{context}

USER QUESTION: {question}

Provide your compliance analysis:"""

        # Get response from LLM
        response = llm.invoke(prompt_text)
        answer = response.content

        # Extract sources (document content snippets)
        sources = [doc.page_content[:200] + "..." for doc in docs]

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
            "documents_searched": len(docs)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing query: {str(e)}")


@app.get("/status")
async def status():
    """Check if policies are loaded"""
    return {
        "policies_loaded": vector_store is not None,
        "status": "ready" if vector_store else "awaiting_policies"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
