# Testing & Validation Guide - Hallucination Prevention System

## Status: Post-Deployment Testing Phase

This guide walks through verifying the Gold Standard Compliance Logic deployment on Render.

---

## Phase 1: Pre-Test Checklist

### Verify Deployment
- ✅ Render logs show successful startup at 09:21:48
- ✅ Backend responding to `/` GET requests (200 OK)
- ✅ Empty vector store correctly returns "No policies uploaded" message
- ✅ Crash-proof error handling implemented (4-layer JSON extraction)

### Backend State
```
Current Render Instance: https://intuition-api.onrender.com
Code Version: Commit 88480fe (latest with Gold Standard + Crash-Proof)
Vector Store: EMPTY (waiting for document upload)
Status: READY FOR TESTING
```

---

## Phase 2: Document Upload Process

### Step 1: Gather Test Documents
Location: `/home/stu/Projects/intuition lab test docs for compliance/`

**Required Files**:
1. `Global_Code_of_Business_Conduct_2025.docx`
   - **Scope**: GLOBAL
   - **Karaoke Policy**: None mentioned (activity not restricted)

2. `Global_Travel_and_Expense_Policy.docx`
   - **Scope**: GLOBAL
   - **Karaoke Policy**: None mentioned (activity not restricted)

3. `Regional_Addendum_APAC_High_Risk.docx`
   - **Scope**: APAC only (China, Japan, Vietnam, Indonesia)
   - **Karaoke Policy**: PROHIBITED
   - **Germany Status**: NOT in APAC scope

### Step 2: Access Compliance Frontend
1. Navigate to: https://intuition-lab.vercel.app/compliance
2. You should see the upload interface with:
   - File drag-drop zone
   - "Process Documents" button
   - Status indicators

### Step 3: Upload Documents
1. Select all 3 test documents
2. Click "Process Documents"
3. Wait for processing indicator to complete
4. Observe console for:
   ```
   ✅ Documents processed successfully
   ✅ Metadata extracted with scopes: GLOBAL, GLOBAL, APAC
   ✅ Vector store initialized with X chunks
   ```

### Step 4: Verify Upload Success
Expected frontend feedback:
- Green checkmark on upload
- Count of processed documents: "3 files processed"
- System ready for queries

---

## Phase 3: Hallucination Prevention Test Case

### Test Query
```
Question: "I have two client entertainment events coming up.
First, I am taking a client in Germany to a Karaoke bar.
Second, I am taking a client in Japan to a Karaoke bar.
Please classify the risk for each event."
```

### Expected Output - CRITICAL VALIDATION

#### For Germany (Non-APAC)
```json
{
  "Germany": {
    "risk_level": "LOW",
    "action": "APPROVE",
    "violation_summary": "No explicit prohibition for Germany",
    "compliance_notes": "APAC-specific policy does not apply to Germany"
  }
}
```

**What this proves**:
- ✅ System correctly filtered out APAC-scoped documents
- ✅ Only GLOBAL policies evaluated (no restrictions)
- ✅ NO hallucination like "including Germany and Japan"
- ✅ Architectural filtering working correctly

#### For Japan (In APAC)
```json
{
  "Japan": {
    "risk_level": "CRITICAL",
    "action": "BLOCK",
    "violation_summary": "Karaoke PROHIBITED in APAC region",
    "compliance_notes": "Regional Addendum explicitly forbids Karaoke in Japan"
  }
}
```

**What this proves**:
- ✅ System correctly applied APAC-scoped documents to Japan
- ✅ Karaoke correctly identified as prohibited
- ✅ Proper risk classification (CRITICAL)
- ✅ Separate analysis per location working

### ANTI-PATTERNS to Watch For
❌ **Hallucination Signs** (System is BROKEN if you see these):
- Germany output mentions "APAC" or "Karaoke prohibited"
- Output includes phrase "including Germany and Japan"
- Single unified analysis instead of separate location assessments
- Japan shows "LOW" or "MODERATE" instead of "CRITICAL"

---

## Phase 4: Response Validation Checklist

### Backend Response Structure
```json
{
  "answer": "string - natural language explanation",
  "risk_classification": {
    "risk_level": "CRITICAL|HIGH|MODERATE|LOW",
    "action": "BLOCK|ESCALATE|FLAG|APPROVE",
    "violation_summary": "one-line summary",
    "detailed_analysis": "multi-paragraph explanation"
  },
  "sources": [
    {"document": "filename", "page": 1, "content": "...excerpt..."}
  ]
}
```

### Frontend Display Verification
1. **Risk Card Color**
   - Germany: Green (LOW)
   - Japan: Red (CRITICAL)

2. **Action Buttons**
   - Germany: Shows "Accept Compliance" button
   - Japan: Shows "Escalate to Compliance Officer" button

3. **Source Citations**
   - Germany: Should cite "Global_Code_of_Business_Conduct_2025.docx" or "Global_Travel_and_Expense_Policy.docx"
   - Japan: Should cite "Regional_Addendum_APAC_High_Risk.docx"

4. **Text Content**
   - No markdown formatting visible
   - No raw JSON showing in detailed_analysis
   - Clean, readable compliance language

---

## Phase 5: Additional Validation Tests

### Test Case 2: Single Location - Germany Only
**Query**: "Can I take a client to Karaoke in Germany?"

**Expected**:
- risk_level: LOW
- Sources: Only GLOBAL documents
- APAC document should NOT be cited

### Test Case 3: Single Location - Japan Only
**Query**: "Can I take a client to Karaoke in Japan?"

**Expected**:
- risk_level: CRITICAL
- Sources: Both GLOBAL (if applicable) and APAC documents
- Specific mention of Karaoke prohibition

### Test Case 4: Different Activity - Germany
**Query**: "Can I take a client to a nightclub in Germany?"

**Expected**:
- risk_level: LOW (not in APAC scope)
- No APAC policies applied

### Test Case 5: Different Activity - Japan
**Query**: "Can I take a client to a nightclub in Japan?"

**Expected**:
- risk_level: CRITICAL (nightclubs also prohibited in APAC)
- APAC document cited

---

## Phase 6: System Behavior Validation

### Console Logs to Monitor

**Backend (Render logs)**:
```
INFO: Processing query with X documents
INFO: Filtered to Y documents for regions: ["user_region"]
INFO: Analyzing with Gold Standard Pipeline
INFO: Risk assessment: [risk_level]
```

**Frontend (Browser console)**:
```
✅ Query submitted
✅ Waiting for backend response...
✅ Response received: 200 OK
✅ Parsed compliance data:
   - Risk Level: CRITICAL
   - Action: BLOCK
   - Sources: [Array of 1]
```

**No Error Signs**:
- ❌ No 500 Server Error
- ❌ No "JSON parse failed" messages
- ❌ No undefined values in response
- ❌ No uncaught exceptions in console

---

## Phase 7: System Architecture Validation

### Metadata Extraction Verification
When documents upload, backend should extract scopes as:

```python
{
  "Global_Code_of_Business_Conduct_2025.docx": ["GLOBAL"],
  "Global_Travel_and_Expense_Policy.docx": ["GLOBAL"],
  "Regional_Addendum_APAC_High_Risk.docx": ["APAC"]
}
```

**NOT**:
```python
{
  "Regional_Addendum_APAC_High_Risk.docx": ["APAC", "GLOBAL"]  # ❌ WRONG
}
```

### Document Filtering Verification
When querying with Germany:

```python
# CORRECT filtering:
- GLOBAL docs → INCLUDED (apply everywhere)
- APAC docs → EXCLUDED (doesn't match Germany)

# WRONG filtering:
- APAC docs → INCLUDED (would cause hallucination)
```

### Hallucination Prevention Layers

**Layer 1 - Strict Filtering** (main defense)
- Implemented in: `filter_documents_by_regions()` lines 275-315
- Verifies: APAC docs excluded from non-APAC queries

**Layer 2 - Prompt Constraints** (secondary defense)
- Implemented in: `RISK_OFFICER_PROMPT` lines 62-101
- Verifies: LLM explicitly told not to infer scope

**Layer 3 - Post-Processing** (tertiary defense)
- Implemented in: `_remove_hallucinations_from_json()` lines 345-404
- Verifies: Catches remaining patterns like ", including [Location]"

**Layer 4 - Crash-Proof Handling** (reliability)
- Implemented in: `extract_json_from_response()` lines 291-342
- Verifies: Never crashes, always returns valid response

---

## Phase 8: Rollback Procedures

If hallucinations still appear:

### Option 1: Check Code Deployment
```bash
# Verify latest commit on Render
# Should show: Commit 88480fe (Gold Standard + Crash-Proof)
```

### Option 2: Force Redeploy
```bash
# GitHub → Render auto-deploys on push
git push origin main  # This triggers Render redeploy
```

### Option 3: Check Metadata Extraction
```bash
# If documents uploaded with wrong scopes,
# Clear vector store and re-upload with fresh metadata extraction
```

### Option 4: Review Logs
```bash
# Render dashboard → Logs → Check for errors
# Look for: "APAC docs filtered" or hallucination warnings
```

---

## Success Criteria

✅ **System is WORKING correctly when**:
1. Germany query shows LOW risk, cites GLOBAL docs only
2. Japan query shows CRITICAL risk, cites APAC docs
3. No hallucinations like "including Germany and Japan"
4. Separate assessments for each location
5. No 500 errors
6. Frontend displays colors correctly

❌ **System has ISSUES if**:
1. Germany shows CRITICAL risk (hallucination)
2. Single unified analysis instead of per-location (scope filtering broken)
3. APAC policy applied to Germany (metadata wrong)
4. 500 Server Error (crash-proof layer failed)
5. Raw JSON visible in response (parser issue)

---

## Documentation References

### Code Files with Implementation
- **Strict Filtering**: `/home/stu/Projects/intuition-api/main.py:275-315`
- **Risk Officer Prompt**: `/home/stu/Projects/intuition-api/main.py:62-101`
- **Hallucination Regex**: `/home/stu/Projects/intuition-api/main.py:345-404`
- **Crash-Proof JSON**: `/home/stu/Projects/intuition-api/main.py:291-342`
- **Frontend Parser**: `/home/stu/Projects/intuition-lab/src/utils/complianceParser.js:11-34`

### Previous Summaries
- **AUDIT_FIX_SUMMARY.md**: Explains problem and initial fixes
- **BEFORE_AFTER_COMPARISON.md**: Shows prompt changes
- **REFACTORING_GUIDE.md**: Architecture details

---

## Next Steps

1. **Upload Documents** (user action)
   - Navigate to compliance page
   - Select 3 test documents
   - Click "Process Documents"

2. **Submit Test Query** (user action)
   - Query about Germany and Japan Karaoke
   - Observe separate risk assessments

3. **Validate Output** (use this checklist)
   - Germany = LOW/APPROVE
   - Japan = CRITICAL/BLOCK
   - No hallucinations

4. **Document Results**
   - Screenshots of successful output
   - Console logs showing no errors
   - Confirmation that system is production-ready

---

*Created: December 3, 2025*
*Status: Post-Deployment Testing Guide*
*Reference: Commit 88480fe (Latest)*
