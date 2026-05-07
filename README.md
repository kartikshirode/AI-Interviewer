# AI Interviewer

A fully automated AI-powered voice interview platform for conducting technical interviews. Features real-time voice conversation with AI, video recording, speech-to-text transcription, AI answer evaluation, and proctoring - completely free to use.

## Features  

### For Recruiters
- Create interviews with custom topics and questions
- Share interview links with candidates
- View and manage candidate responses
- AI-powered answer evaluation with scores
- Comprehensive reporting dashboard
- Video playback of recorded interviews

### For Candidates
- Simple registration via interview link
- **Voice-based AI interview** - Talk directly with an AI interviewer
- Mandatory system check before interview
- Voice verification - speak a phrase to verify mic works
- Video and audio recording during interview
- Screen sharing (required)
- Real-time proctoring feedback

### AI & Automation
- **Voice Interview**: Browser Web Speech API for live transcription + TTS, plus `MediaRecorder` for audio capture. No third-party voice service.
- **Speech-to-Text**: Local processing with faster-whisper (free, runs offline)
- **Question generation & evaluation**: Google Gemini (`gemini-flash-latest`)
- **Proctoring**: Tab switching detection, clipboard monitoring, persisted as `ProctoringEvent` rows; risk scoring via the in-process `RiskEngine`

## Tech Stack

| Component | Technology |
|-----------|------------|
| Backend | FastAPI, Python 3.12+, SQLite |
| Frontend | Next.js 16, React 19, Tailwind v4 |
| Voice flow | Browser Web Speech API + MediaRecorder (no LiveKit) |
| Speech-to-Text | faster-whisper (local, free) |
| AI | Google Gemini `gemini-flash-latest` (free tier) |
| Database | SQLite (dev) — `ai_interviewer.db` is gitignored, regenerated on startup |

## Getting Started

### Prerequisites
- Python 3.12+
- Node.js 18+
- npm

### Step 1: Clone & Install Dependencies

```bash
# Backend
cd backend
pip install -r requirements.txt

# Frontend
cd frontend
npm install
```

### Step 2: Configure API Keys

Create a `backend/.env` file:

```env
# Gemini API (for AI evaluation - free tier)
GEMINI_API_KEY=your-gemini-api-key

```
Get free keys:
- Gemini API: https://aistudio.google.com/app/apikey

### Step 3: Start Backend

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

Backend runs at: http://localhost:8000  
API Docs: http://localhost:8000/docs

### Step 4: Start Frontend

```bash
cd frontend
npm run dev
```

Frontend runs at: http://localhost:3000

## Interview Flow

### Candidate Flow
```
1. Open interview link
2. Register with name/email
3. System Check (mandatory):
   - Camera permission
   - Microphone permission  
   - Screen share permission
   - Internet speed test
4. Voice Verification (mandatory):
   - Speak phrase: "I am ready to start the interview"
   - Record and verify voice
5. Voice Interview with AI:
   - AI asks questions verbally
   - Candidate answers by voice (push-to-talk)
   - Video is recorded
6. Interview Complete
```

### Recruiter Flow
```
1. Sign up/Login at /recruiter/login
2. Create interview with topics
3. Copy shareable link
4. After candidate completes:
   - Click "Transcribe" to convert video to text
   - Click "Evaluate" to get AI scores
   - View full report with scores and risk assessment
```

## API Endpoints

### Authentication
- `POST /api/v1/auth/signup` - Recruiter signup
- `POST /api/v1/auth/login` - Recruiter login

### Interviews
- `POST /api/v1/interviews/` - Create interview
- `GET /api/v1/interviews/` - List interviews
- `GET /api/v1/interviews/{id}/candidates` - List candidates

### Candidate
- `POST /api/v1/candidate/interview/{id}/register` - Register candidate
- `GET /api/v1/candidate/interview/{link}` - Get interview by link
- `POST /api/v1/candidate/answer` - Submit answer
- `POST /api/v1/candidate/candidate/{id}/transcribe-all` - Transcribe all answers
- `POST /api/v1/candidate/candidate/{id}/evaluate` - Evaluate with AI
- `GET /api/v1/candidate/candidate/{id}/report` - Get full report

### Topics
- `GET /api/v1/topics/` - List topics with their curated skill catalogues
- `GET /api/v1/topics/general-skills` - General soft skills (leadership, communication, …)
- `POST /api/v1/topics/` - Create custom topic (recruiter-only)

### Question previews
- `GET /api/v1/interviews/sample-questions/{topic_id}?difficulty=&count=&skills=&regenerate=`
- `GET /api/v1/interviews/sample-questions/by-name/{topic_name}?…` (custom "Other" topic)

### Proctoring
- `POST /api/v1/candidate/candidate/{id}/proctoring` - Candidate submits a batch of proctoring events (candidate-token auth)
- `POST /api/v1/candidate/candidate/{id}/proctoring/report` - Recruiter pulls the risk report (recruiter-token auth)

## Cost

This project is **completely free** to use:

- **faster-whisper**: Runs locally, no API costs
- **Gemini API**: Free tier (15 requests/min, 1M tokens/month). The DB-backed question bank reuses generated questions across recruiters so token usage scales with novelty, not interview count.
- **SQLite**: Free, no setup required

## Project Structure

```
AI-Interviewer/
├── backend/
│   └── app/
│       ├── routers/           # API endpoints
│       │   ├── auth.py        # Authentication (recruiter + candidate tokens)
│       │   ├── interviews.py  # Interview CRUD + question bank resolver
│       │   ├── topics.py      # Topic catalogue + general-skills
│       │   ├── candidate.py   # Candidate flow + proctoring + reports
│       │   └── video.py       # Video playback (recruiter-only)
│       ├── services/          # Business logic
│       │   ├── speech_service.py      # Speech-to-text (faster-whisper)
│       │   ├── evaluation_service.py  # Answer scoring + percentile bands
│       │   ├── question_generator.py  # Gemini-backed question generator
│       │   ├── skills.py              # GENERAL_SKILLS + skills_key normalization
│       │   └── risk_engine.py         # Proctoring → risk level
│       ├── models/            # Database models (incl. QuestionBank, ProctoringEvent)
│       └── core/              # Config, security
├── frontend/
│   └── src/
│       ├── app/
│       │   ├── page.tsx                    # Home page
│       │   ├── recruiter/                   # Recruiter pages
│       │   │   ├── login/
│       │   │   └── dashboard/
│       │   └── interview/                  # Candidate pages
│       │       └── [link]/
│       ├── hooks/
│       │   ├── useProctoring.ts    # Proctoring
│       │   ├── useSystemCheck.ts   # Device checks
│       │   └── useVoiceVerification.ts # Voice verify
│       └── services/
│           └── api.ts            # API client
└── README.md
```

## License

MIT License - Free to use for any purpose.
