# Phase 4: Real-Time Media System - COMPLETED

## Summary

This phase implements video, audio, and screen capture for the interview system.

### Completed Tasks

1. **Webcam Capture**
   - Request camera permission
   - Live video preview during interview
   - Video recording to WebM format

2. **Microphone Capture**
   - Audio recording synced with video
   - MediaRecorder API for local recording

3. **Screen Sharing**
   - Toggle screen share on/off
   - Live preview of shared screen
   - Recording of screen share

4. **Video Storage**
   - Backend endpoint accepts video uploads
   - Videos saved to `backend/uploads/`
   - Video path stored in database

---

## How to Run Phase 4

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

### Step 3: Test Media Capture
1. Go to http://localhost:3000/recruiter/login
2. Create an interview with topics
3. Copy the interview link
4. Open link as candidate
5. Start interview
6. Verify:
   - Camera preview shows in sidebar
   - "Recording" indicator appears
   - Can toggle screen share
   - Answer questions (video is saved per question)

---

## Current State

### Working Features
- Live webcam preview during interview
- Video recording (MediaRecorder API)
- Screen sharing with toggle
- Video upload to backend
- Videos stored in `backend/uploads/`

### Backend Changes
- Added video upload to `/api/v1/candidate/answer`
- Added `video_path` column to Answer model
- Created `backend/uploads/` directory

### Frontend Changes
- Added video element for camera preview
- Added video element for screen share
- Added MediaRecorder for video capture
- Updated submit to send video blob

---

## Next Phase: Phase 5 - Speech Processing

### What's Included
- Speech-to-text transcription
- Audio extraction from video
- Transcript storage in database

### Before Moving to Phase 5
1. Test complete interview with video recording
2. Verify videos are saved in uploads folder
3. Test screen sharing functionality

---

## LiveKit Integration (For Real-Time Streaming)

If you want to use LiveKit for real-time streaming instead of local recording:

### Backend Setup
```bash
# Install LiveKit server
pip install livekit
pip install livekit-api
```

### Files to Create/Modify:
1. `backend/app/services/livekit_service.py` - Token generation
2. `backend/app/routers/livekit.py` - New router for LiveKit endpoints
3. Update `backend/app/main.py` to include LiveKit router

### Frontend Updates:
1. Install: `npm install livekit-client`
2. Update `frontend/src/app/interview/[link]/page.tsx`:
   - Import: `import { LiveKitRoom, RoomEvent } from 'livekit-client'`
   - Connect to room on interview start
   - Publish camera/microphone tracks
   - Subscribe to remote tracks (for AI interviewer)

### Quick Integration Points:
- Token endpoint: `POST /api/v1/livekit/token`
- Room connection in: `startInterview()` function
- Track handling in: `<VideoTrack />` components
