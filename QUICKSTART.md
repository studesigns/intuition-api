# Compliance Risk Engine API - Quick Start Guide

## 🎯 What Was Built

Your Python backend API is fully configured and ready to deploy. All files follow the specification from the Master Prompt.

## 📁 Project Structure

```
intuition-api/
├── main.py              # FastAPI application with all endpoints
├── requirements.txt     # Python dependencies (FastAPI, LangChain, FAISS, OpenAI)
├── Dockerfile          # Docker containerization for Render
├── .env.example        # Environment variables template
├── .gitignore          # Git ignore for venv, __pycache__, .env
├── README.md           # Complete documentation
└── QUICKSTART.md       # This file
```

## 🚀 Local Testing (3 Steps)

### 1. Create Virtual Environment
```bash
cd /home/stu/Projects/intuition-api
python3 -m venv venv
source venv/bin/activate
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Set Up Environment & Run
```bash
cp .env.example .env
# Edit .env and add your OpenAI API key: OPENAI_API_KEY=sk-proj-...
python main.py
```

Server runs on `http://localhost:8000`

## 📚 API Endpoints

### Health Check
```bash
curl http://localhost:8000/
# Returns: {"status": "operational", ...}
```

### Upload Policies
```bash
curl -X POST http://localhost:8000/upload \
  -F "files=@policy.pdf" \
  -F "files=@another_policy.pdf"
# Returns: {"status": "success", "chunks": N, ...}
```

### Query Compliance
```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question": "Is remote work allowed?"}'
# Returns: {"answer": "...", "compliance_status": "...", ...}
```

### Check Status
```bash
curl http://localhost:8000/status
# Returns: {"policies_loaded": true/false, ...}
```

## 🐳 Deploy to Render (One Click)

### 1. Push to GitHub
```bash
cd /home/stu/Projects/intuition-api
git remote add origin https://github.com/studesigns/intuition-api.git
git branch -M main
git push -u origin main
```

### 2. Create on Render
- Go to https://dashboard.render.com
- Click "New" → "Web Service"
- Select GitHub repo: `studesigns/intuition-api`
- Set name: `intuition-api`
- Environment: Docker
- Click "Create"

### 3. Add Environment Variable
In Render dashboard:
- Key: `OPENAI_API_KEY`
- Value: `sk-proj-...your-key...`

Render automatically builds and deploys! 🎉

You'll get a public URL like: `https://intuition-api.onrender.com`

## 🔌 Connect to Frontend

Update `src/context/VoiceContext.jsx` or compliance page in Intuition Lab:

```javascript
const API_BASE = process.env.REACT_APP_API_URL || "http://localhost:8000";

// Upload policies
async function uploadPolicies(files) {
  const formData = new FormData();
  files.forEach(file => formData.append("files", file));

  const response = await fetch(`${API_BASE}/upload`, {
    method: "POST",
    body: formData
  });
  return response.json();
}

// Query compliance
async function queryCompliance(question) {
  const response = await fetch(`${API_BASE}/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question })
  });
  return response.json();
}
```

## ✨ Key Features

✅ **Risk Officer Persona** - Strict compliance analysis
✅ **FAISS Vector Store** - Fast semantic search
✅ **Source Citations** - Links to specific policies
✅ **Risk Detection** - Automatic compliance violation flagging
✅ **Dockerized** - One-click Render deployment
✅ **CORS Enabled** - Ready for React frontend

## 🔒 Security Notes

**Current MVP:**
- In-memory vector store (resets on restart)
- No authentication needed
- CORS allows all origins

**For Production:**
- Add user authentication
- Persist vector store to database
- Restrict CORS to frontend domain
- Add rate limiting

## 📖 Full Documentation

See `README.md` for:
- Complete API reference
- Detailed deployment instructions
- Troubleshooting guide
- Future improvements

## ❓ Next Steps

1. **Test Locally** - Follow steps above to run `python main.py`
2. **Create .env** - Add your OpenAI API key
3. **Upload Sample PDFs** - Test with compliance documents
4. **Deploy to Render** - Push to GitHub, deploy on Render
5. **Connect Frontend** - Update Intuition Lab to call the API

## 🎯 This API is "Render-Ready"

The Dockerfile is fully configured. Just push to GitHub and Render will:
- Auto-detect the Dockerfile
- Build the image
- Deploy with environment variables
- Provide a public URL

**No additional configuration needed!**

---

**Ready to test locally or deploy? You're all set! 🚀**
