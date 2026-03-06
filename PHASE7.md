# Phase 7: AI Proctoring System - COMPLETED

## Summary

This phase implements browser-based proctoring to detect cheating during interviews.

### Completed Tasks

1. **Tab Switching Detection**
   - Monitors visibility change events
   - Detects window blur
   - Counts tab switches

2. **Clipboard Monitoring**
   - Detects copy events (Ctrl+C, context menu)
   - Detects paste events (Ctrl+V, context menu)
   - Counts clipboard operations

3. **Keyboard Shortcut Detection**
   - Detects new tab (Ctrl+T)
   - Detects copy/paste shortcuts
   - Logs all suspicious shortcuts

4. **Face Detection Hook** (placeholder)
   - Ready for face-api.js integration
   - Detects multiple faces
   - Eye gaze tracking

5. **Screen Text Detection Hook** (placeholder)
   - Ready for Tesseract.js OCR
   - Suspicious keyword detection
   - Screen capture analysis

---

## How to Run Phase 7

### Prerequisites
- Backend and Frontend running

### Step 1: Start Backend
```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

### Step 2: Start Frontend
```bash
cd frontend
npm run dev
```

### Step 3: Test Proctoring
1. Start an interview as candidate
2. Try switching tabs (should be detected)
3. Try copying/pasting (should be detected)
4. Complete interview
5. Check proctoring report API:

```bash
# Get proctoring report
curl -X POST "http://localhost:8000/api/v1/candidate/candidate/1/proctoring/report"
```

---

## Current State

### Working Features
- Tab switching detection
- Clipboard copy/paste detection
- Keyboard shortcut detection
- Risk level calculation (low/medium/high)
- Events logging

### Risk Score Calculation
```
Tab Switch = 10 points
Clipboard Copy = 5 points
Clipboard Paste = 10 points
Face Away = 5 points
Multiple Face = 20 points
Suspicious Text = 15 points

Risk Levels:
- 0-30: Low
- 30-60: Medium
- 60+: High
```

### New API Endpoints
- `POST /api/v1/candidate/candidate/{id}/proctoring` - Save proctoring data
- `POST /api/v1/candidate/candidate/{id}/proctoring/report` - Get risk report

### Frontend Changes
- Created `frontend/src/hooks/useProctoring.ts`
- Integrated proctoring in interview page
- Real-time risk level display

---

## Next Phase: Phase 8 - Cheating Risk Engine

### What's Included
- Combine all proctoring signals
- Calculate overall risk score
- Flag suspicious candidates

### Before Moving to Phase 8
1. Test tab switching detection
2. Test clipboard detection
3. Verify events are logged

---

## Advanced Features (Optional)

### Face Detection
To enable face detection, install face-api.js:
```bash
cd frontend
npm install face-api.js
```

Then update the `useFaceDetection` hook in `useProctoring.ts`.

### OCR for Screen Text
To enable screen text detection, install Tesseract.js:
```bash
cd frontend
npm install tesseract.js
```

Then update the `useScreenTextDetection` hook in `useProctoring.ts`.

### Live Video Analysis
For real-time face/eye tracking during interview:
1. Use face-api.js for face detection
2. Use a TensorFlow.js model for eye gaze
3. Process video frames in a web worker
