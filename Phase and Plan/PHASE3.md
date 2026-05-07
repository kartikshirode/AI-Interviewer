# Phase 3: Candidate Interview System - COMPLETED

## Summary

This phase implements the complete candidate interview flow from registration to answering questions.

### Completed Tasks

1. **Backend API** - Added candidate endpoints:
   - Get interview by link
   - Register candidate
   - Get questions for interview
   - Start interview
   - Submit answer
   - Complete interview

2. **Candidate Registration** - New page at `/interview/{link}`:
   - Interview details display
   - Name/email registration form
   - Permission check (camera/mic)

3. **Interview UI** - Question flow:
   - One question at a time display
   - 2-minute timer per question
   - Text input for answers
   - Next question / Submit flow
   - Completion screen

4. **Interview Controller**:
   - Load questions from backend
   - Track current question index
   - Submit answers to backend
   - Handle interview completion

---

## How to Run Phase 3

### Prerequisites
- Backend and Frontend running from previous phases

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

### Step 3: Test Full Flow
1. Go to http://localhost:3000/recruiter/login
2. Create an interview with topics
3. Copy the interview link
4. Open link in new browser/incognito
5. Register as candidate
6. Check permissions
7. Start and complete interview

---

## Current State

### Working Features
- Interview link validation
- Candidate registration (name, email)
- Permission check (camera/mic)
- Question display (one at a time)
- 2-minute timer per question
- Answer submission
- Interview completion

### API Endpoints Added
- `GET /api/v1/candidate/interview/{link}` - Get interview by link
- `POST /api/v1/candidate/interview/{id}/register` - Register candidate
- `GET /api/v1/candidate/interview/{id}/questions` - Get questions
- `POST /api/v1/candidate/interview/{id}/start` - Start interview
- `POST /api/v1/candidate/answer` - Submit answer
- `POST /api/v1/candidate/interview/{id}/complete` - Complete interview

### Database Changes
- Candidates table now stores interview responses
- Answers table stores transcripts

---

## Next Phase: Phase 4 - Real-Time Media System

### What's Included
- Webcam video capture
- Microphone audio capture
- Screen sharing
- Media recording storage

### Before Moving to Phase 4
1. Test complete interview flow
2. Verify answers are saved
3. Test with multiple questions

### Important Notes for Next Phase
- Currently answers are text input only
- Phase 5 will add speech-to-text
- Phase 4 will add actual media recording
- Video/audio used for proctoring in later phases

---

## LiveKit Integration Point (For Phase 4+)

When integrating LiveKit for real-time audio/video, add the following:

### Backend - New file: `backend/app/services/livekit_service.py`
```python
# LiveKit service for generating room tokens
# Endpoint: POST /api/v1/candidate/interview/{id}/token
```

### Frontend - Update: `frontend/src/app/interview/[link]/page.tsx`
- Import LiveKit client: `import { LiveKitRoom, RoomEvent } from 'livekit-client'`
- Add video element in the interview UI
- Connect to LiveKit room during interview
- Handle track subscription for webcam/mic/screen

### Where to add in candidate page:
1. In `checkPermissions()` - After getting media stream, connect to LiveKit room
2. In interview state - Display video element with `useTrack` hook
3. Add screen share toggle
4. Handle room disconnection on interview complete
