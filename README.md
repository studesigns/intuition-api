# Compliance Risk Engine API

The backend API powering the Intuition Lab Compliance Risk Engine. Built with FastAPI and LangChain, it provides compliance policy analysis using AI-powered document retrieval and risk assessment.

## Architecture

- **Framework**: FastAPI (Python)
- **Vector Store**: FAISS (Facebook AI Similarity Search)
- **Embeddings**: OpenAI text-embedding-ada-002
- **LLM**: GPT-3.5-turbo / GPT-4
- **Deployment**: Render (Docker containerized)
- **Frontend**: React/Vercel (Intuition Lab Dashboard)

## Features

✅ **PDF Policy Upload** - Ingest compliance documents
✅ **Semantic Search** - Find relevant policies using AI embeddings
✅ **Risk Detection** - Identify compliance violations automatically
✅ **Source Citations** - Link answers back to specific policy sections
✅ **Risk Officer Persona** - Strict, conservative compliance analysis
✅ **CORS Enabled** - Ready to connect with frontend

## Local Development

### Prerequisites

- Python 3.9+
- OpenAI API key (from https://platform.openai.com)
- pip package manager

### Setup

1. **Clone and enter the project**
   ```bash
   cd /home/stu/Projects/intuition-api
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**
   ```bash
   cp .env.example .env
   # Edit .env and add your OpenAI API key
   ```

5. **Run the server**
   ```bash
   python main.py
   ```

   Server will start on `http://localhost:8000`

### API Documentation

Once running, visit:
- **Interactive API Docs**: http://localhost:8000/docs (Swagger UI)
- **Alternative Docs**: http://localhost:8000/redoc (ReDoc)

## Endpoints

### `GET /`
Health check endpoint.

**Response:**
```json
{
  "status": "operational",
  "service": "Compliance Risk Engine API",
  "version": "1.0.0"
}
```

### `POST /upload`
Upload PDF policy documents to build the knowledge base.

**Request:**
- Form data with `files` field (multiple PDF files accepted)

**Response:**
```json
{
  "status": "success",
  "chunks": 150,
  "files_processed": 3,
  "message": "Successfully processed 3 PDF file(s) into 150 chunks"
}
```

**cURL Example:**
```bash
curl -X POST http://localhost:8000/upload \
  -F "files=@policy1.pdf" \
  -F "files=@policy2.pdf"
```

### `POST /query`
Query the compliance policies with a question.

**Request:**
```json
{
  "question": "Is remote work allowed for sensitive data handling?"
}
```

**Response:**
```json
{
  "answer": "COMPLIANCE STATUS: RISK DETECTED\n\nANALYSIS: Remote work for sensitive data handling is explicitly prohibited in Section 3.2.1 of the Data Protection Policy...",
  "sources": [
    "Section 3.2.1: Remote work restrictions...",
    "Section 4.1: Data protection requirements..."
  ],
  "compliance_status": "RISK DETECTED",
  "documents_searched": 5
}
```

**cURL Example:**
```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question": "Is remote work allowed for sensitive data handling?"}'
```

### `GET /status`
Check if policies are loaded.

**Response:**
```json
{
  "policies_loaded": true,
  "status": "ready"
}
```

## Deployment to Render

### Step 1: Push to GitHub

```bash
cd /home/stu/Projects/intuition-api
git add .
git commit -m "Initial commit: Compliance Risk Engine API"
git remote add origin https://github.com/studesigns/intuition-api.git
git push -u origin main
```

### Step 2: Deploy on Render

1. Go to https://dashboard.render.com
2. Click "New" → "Web Service"
3. Select your GitHub repo `studesigns/intuition-api`
4. Configure:
   - **Name**: `intuition-api`
   - **Environment**: `Docker`
   - **Build Command**: Leave empty (uses Dockerfile)
   - **Start Command**: Leave empty (uses Dockerfile)
   - **Instance Type**: Free (for testing) or Starter+ (production)

5. Add Environment Variables:
   - Key: `OPENAI_API_KEY`
   - Value: Your OpenAI API key

6. Click "Create Web Service"

Render will automatically:
- Build the Docker image
- Deploy the service
- Provide a public URL

### Step 3: Connect to Frontend

Update your React frontend to use the Render API URL:

```javascript
const API_BASE = "https://intuition-api.onrender.com";

// Upload policies
const uploadResponse = await fetch(`${API_BASE}/upload`, {
  method: "POST",
  body: formData
});

// Query policies
const queryResponse = await fetch(`${API_BASE}/query`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ question: userQuestion })
});
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | ✅ | OpenAI API key for embeddings and LLM |
| `RENDER_SERVICE_NAME` | ❌ | Auto-set by Render |

## Project Structure

```
intuition-api/
├── main.py              # FastAPI application
├── requirements.txt     # Python dependencies
├── Dockerfile          # Container configuration
├── .env.example        # Environment template
├── .gitignore          # Git ignore rules
├── README.md           # This file
└── .git/               # Git repository
```

## Testing

### Test the API locally with Python

```python
import requests
import json

BASE_URL = "http://localhost:8000"

# Test health check
print(requests.get(f"{BASE_URL}/").json())

# Test status
print(requests.get(f"{BASE_URL}/status").json())

# Test query (after uploading policies)
response = requests.post(
    f"{BASE_URL}/query",
    json={"question": "What are the data protection requirements?"}
)
print(json.dumps(response.json(), indent=2))
```

## Troubleshooting

### "OpenAI API key not configured"
- Make sure `.env` file exists with `OPENAI_API_KEY`
- Run locally: `export OPENAI_API_KEY=sk-...` (Linux/Mac)
- Run locally: `set OPENAI_API_KEY=sk-...` (Windows)
- Render: Add environment variable in dashboard

### "No policies uploaded"
- Call `/upload` endpoint first with PDF files
- Check that files are valid PDFs
- Verify `GET /status` shows `"policies_loaded": true`

### "CORS errors from frontend"
- CORS is enabled for all origins (`allow_origins=["*"]`)
- If needed, restrict to specific frontend URL:
  - Edit `main.py` line 21: `allow_origins=["https://intuition-lab.vercel.app"]`

### "Timeout errors"
- LLM queries can take 10-30 seconds
- Increase timeout in frontend fetch calls
- Consider using longer-running plan on Render

## Security Considerations

⚠️ **Current MVP Implementation:**
- Vector store is in-memory only (lost on server restart)
- No user authentication or rate limiting
- Policies are not persisted to database
- CORS allows all origins

📋 **Production Enhancements:**
- Add authentication (JWT tokens)
- Persist vector store to database
- Implement rate limiting
- Restrict CORS to specific domain
- Add input validation and sanitization
- Implement audit logging

## Future Improvements

- [ ] Persist vector store to PostgreSQL
- [ ] Add user authentication and multi-tenant support
- [ ] Implement caching for frequent queries
- [ ] Add document versioning and audit trails
- [ ] Support for more file types (Word, PowerPoint)
- [ ] Real-time policy change notifications
- [ ] Advanced analytics dashboard

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Review API docs at `/docs`
3. Check server logs on Render dashboard

## License

Internal use only - Intuition Innovation Lab

---

**Version**: 1.0.0
**Last Updated**: December 2, 2025
**Status**: Ready for Render deployment
# Deployment fix Wed Dec  3 16:01:19 GMT 2025
