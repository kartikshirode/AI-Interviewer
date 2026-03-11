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
- **Voice Interview**: LiveKit for real-time voice conversation
- **Speech-to-Text**: Local processing with faster-whisper (free, runs offline)
- **Answer Evaluation**: Google Gemini API (free tier available)
- **Proctoring**: Tab switching detection, clipboard monitoring, risk scoring

## Tech Stack

| Component | Technology |
|-----------|------------|
| Backend | FastAPI, Python, SQLite |
| Frontend | Next.js 14, React, Tailwind CSS |
| Voice | LiveKit (free tier) |
| Speech-to-Text | faster-whisper (local, free) |
| AI Evaluation | Google Gemini API (free tier) |
| Database | SQLite (dev) |

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

# LiveKit (for voice interview - free tier)
# Get free keys at https://livekit.io
LIVEKIT_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=your-api-key
LIVEKIT_API_SECRET=your-api-secret
```

Get free keys:
- Gemini API: https://aistudio.google.com/app/apikey
- LiveKit: https://livekit.io

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

### Voice
- `POST /api/v1/voice/token` - Get LiveKit token for voice interview

## Cost

This project is **completely free** to use:

- **LiveKit**: Free tier (unlimited minutes for development)
- **faster-whisper**: Runs locally, no API costs
- **Gemini API**: Free tier (15 requests/min, 1M tokens/month)
- **SQLite**: Free, no setup required

## Project Structure

```
AI-Interviewer/
├── backend/
│   └── app/
│       ├── routers/           # API endpoints
│       │   ├── auth.py       # Authentication
│       │   ├── interviews.py # Interview CRUD
│       │   ├── candidate.py # Candidate operations
│       │   ├── voice.py      # LiveKit voice
│       │   └── video.py      # Video playback
│       ├── services/         # Business logic
│       │   ├── speech_service.py      # Speech-to-text
│       │   ├── evaluation_service.py  # AI evaluation
│       │   ├── risk_engine.py         # Proctoring
│       │   └── livekit_service.py     # Voice tokens
│       ├── models/           # Database models
│       └── core/             # Config, security
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
