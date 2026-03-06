# Phase 8: Cheating Risk Engine - COMPLETED

## Summary

This phase implements a comprehensive risk scoring engine that combines all proctoring signals.

### Completed Tasks

1. **Risk Engine Service**
   - Combines all proctoring signals
   - Calculates weighted risk scores
   - Generates detailed risk reports
   - Provides recommendations

2. **Risk Score Weights**
   - Tab Switch: 15 points
   - Window Blur: 10 points
   - Clipboard Copy: 10 points
   - Clipboard Paste: 20 points
   - New Tab: 25 points
   - Face Away: 15 points
   - Multiple Faces: 50 points
   - Suspicious Screen: 30 points

3. **Risk Levels**
   - Low: 0-30 points
   - Medium: 30-60 points
   - High: 60+ points

---

## How to Run Phase 8

### Prerequisites
- Backend running

### Step 1: Start Backend
```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

### Step 2: Test Risk Engine
```bash
# Get comprehensive risk report
curl -X POST "http://localhost:8000/api/v1/candidate/candidate/1/proctoring/report"
```

Example Response:
```json
{
  "risk_score": 45,
  "risk_level": "medium",
  "risk_factors": [
    {
      "event": "clipboard_paste",
      "description": "Text pasted from clipboard",
      "count": 2,
      "points_per_event": 20,
      "total_points": 40
    },
    {
      "event": "tab_switch",
      "description": "Tab switching detected",
      "count": 1,
      "points_per_event": 15,
      "total_points": 15
    }
  ],
  "total_events": 3,
  "recommendation": "Some suspicious behavior detected. Review video recordings carefully before making a decision.",
  "timestamp": 1234567890
}
```

---

## Current State

### Working Features
- Comprehensive risk scoring
- Detailed risk factor breakdown on risk level

- Recommendations based- Risk level stored in candidate record

### Risk Thresholds
| Level | Score Range | Action |
|-------|-------------|--------|
| Low | 0-30 | Proceed with normal evaluation |
| Medium | 30-60 | Review videos carefully |
| High | 60+ | Manual review, consider rejection |

### New Service
- `backend/app/services/risk_engine.py`

---

## Next Phase: Phase 9 - Candidate Report System

### What's Included
- Generate final interview results
- Report includes: candidate name, role, scores, cheating risk

### Before Moving to Phase 9
1. Complete interview with proctoring
2. Test risk report API
3. Verify risk level is saved

---

## Complete Evaluation Pipeline

To evaluate a candidate end-to-end:

```bash
# 1. Transcribe all answers
curl -X POST "http://localhost:8000/api/v1/candidate/candidate/1/transcribe-all"

# 2. Evaluate all answers  
curl -X POST "http://localhost:8000/api/v1/candidate/candidate/1/evaluate"

# 3. Get proctoring report
curl -X POST "http://localhost:8000/api/v1/candidate/candidate/1/proctoring/report"
```

This gives you:
- Technical scores per question
- Communication score
- Final overall score
- Cheating risk level
- Detailed recommendations
