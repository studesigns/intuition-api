# Quick Test Guide - Hallucination Fix Validation

## 🚀 Quick Start (5 minutes)

### Step 1: Upload Documents (2 min)
Go to: **https://intuition-lab.vercel.app/compliance**

Upload these 3 files from `/home/stu/Projects/intuition lab test docs for compliance/`:
- `Global_Code_of_Business_Conduct_2025.docx`
- `Global_Travel_and_Expense_Policy.docx`
- `Regional_Addendum_APAC_High_Risk.docx`

Click "Process Documents" → wait for completion

### Step 2: Test Query (1 min)
Ask this question:
```
I have two client entertainment events coming up.
First, I am taking a client in Germany to a Karaoke bar.
Second, I am taking a client in Japan to a Karaoke bar.
Please classify the risk for each event.
```

### Step 3: Validate Output (2 min)
Check if you see:

✅ **Germany Shows**: GREEN (LOW) - No hallucination
```
Risk: LOW
Action: APPROVE
Summary: No explicit prohibition for Germany
```

✅ **Japan Shows**: RED (CRITICAL) - Correct detection
```
Risk: CRITICAL
Action: BLOCK
Summary: Karaoke PROHIBITED in APAC region
```

---

## 🔴 RED FLAGS (System is broken if you see these)

❌ **Hallucination Pattern**: Germany shows CRITICAL or mentions "APAC"
❌ **Single Analysis**: Only one risk assessment instead of separate ones
❌ **Mixed Locations**: "including Germany and Japan" phrase
❌ **Server Error**: 500 error or "connecting..." message
❌ **Raw JSON**: Code visible in the detailed analysis section

---

## ✅ SUCCESS INDICATORS

✅ Germany = GREEN/LOW (separate assessment)
✅ Japan = RED/CRITICAL (separate assessment)
✅ No "including Germany" hallucinations
✅ Separate source citations for each
✅ Clean readable text (no JSON visible)
✅ No server errors

---

## 🔧 Automated Validation

Run the Python test script:
```bash
cd /home/stu/Projects/intuition-api
python validate_hallucination_fix.py
```

Expected output:
```
✓ [HH:MM:SS] Backend is running
✓ [HH:MM:SS] Vector store ready: 3 documents, X chunks
✓ [HH:MM:SS] Germany Karaoke test PASSED
✓ [HH:MM:SS] Japan Karaoke test PASSED
🎉 All tests passed! Hallucination prevention is working correctly.
```

---

## 📋 Test Checklist

- [ ] Documents uploaded successfully
- [ ] Query submitted without errors
- [ ] Germany shows LOW (green)
- [ ] Japan shows CRITICAL (red)
- [ ] No "including" hallucinations
- [ ] Separate analyses for each location
- [ ] No server errors
- [ ] Text is clean and readable

---

## 💾 What Was Fixed

| Issue | Before | After |
|-------|--------|-------|
| Germany Risk | CRITICAL (hallucination) | LOW (correct) |
| Analysis Type | Single unified | Separate per-location |
| Scope Matching | Allowed inference | Strict extraction only |
| Error Handling | 500 crashes | Always valid response |

---

## 📞 Troubleshooting

**"No policies uploaded" message**
→ Go to compliance page and upload the 3 documents

**"Server Error 500"**
→ Check Render logs: https://dashboard.render.com
→ Verify backend is running: https://intuition-api.onrender.com

**"Still seeing hallucinations"**
→ Documents may have old metadata
→ Clear vector store and re-upload
→ Check document scope headers match expected

**"Response shows raw JSON"**
→ Frontend parser issue
→ Clear browser cache and reload
→ Check browser console for errors

---

## 🎯 Key Metrics

**Hallucination Prevention**: Multi-layer defense
1. **Architectural Filtering** - APAC docs excluded from Germany queries
2. **Prompt Constraints** - LLM explicitly forbidden from inferring scope
3. **Post-Processing** - Regex removes ", including [Location]" patterns
4. **Error Handling** - 4-layer JSON extraction prevents crashes

**Expected Behavior**: Same logic applies to ANY documents, not just these examples

---

## 📚 For More Details

- Full testing guide: `TESTING_AND_VALIDATION.md`
- System architecture: `REFACTORING_GUIDE.md`
- Before/After comparison: `BEFORE_AFTER_COMPARISON.md`
- Fix summary: `AUDIT_FIX_SUMMARY.md`

---

*Last Updated: December 3, 2025*
*Status: Deployment Complete - Ready for Testing*
