# AI Interviewer

A fully automated AI-powered interview platform for conducting technical interviews. Features video recording, speech-to-text transcription, AI answer evaluation, and proctoring - completely free to use.

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
- One-on-one question format with timer
- Video and audio recording during interview
- Screen sharing capability
- Real-time proctoring feedback

### AI & Automation
- **Speech-to-Text**: Local processing with faster-whisper (free, runs offline)
- **Answer Evaluation**: Google Gemini API (free tier available)
- **Proctoring**: Tab switching detection, clipboard monitoring, risk scoring

## Tech Stack

| Component | Technology |
|-----------|------------|
| Backend | FastAPI, Python, SQLite |
| Frontend | Next.js 14, React, Tailwind CSS |
| Speech-to-Text | faster-whisper (local, free) |
| AI Evaluation | Google Gemini API (free tier) |
| Database | SQLite (dev) |

## Getting Started

### Prerequisites
- Python 3.12+
- Node.js 18+
- npm

### Step 1: Clone & Install Backend Dependencies

```bash
cd backend
pip install -r requirements.txt
```

### Step 2: Configure API Keys

Create a `backend/.env` file with your Gemini API key:

```env
GEMINI_API_KEY=your-gemini-api-key
```

Get a free API key at: https://aistudio.google.com/app/apikey

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
npm install
npm run dev
```

Frontend runs at: http://localhost:3000

## How It Works

### 1. Recruiter Creates Interview
1. Go to http://localhost:3000
2. Click "Recruiter Login" → Sign up
3. Create new interview with topics/questions
4. Copy the shareable interview link

### 2. Candidate Takes Interview
1. Open the interview link
2. Register with name/email
3. Allow camera/microphone access
4. Answer questions (video recorded)
5. Submit interview

### 3. Recruiter Reviews
1. Go to Dashboard → View Candidates
2. Click "Transcribe" to convert video to text
3. Click "Evaluate" to get AI scores
4. View full report with scores and risk assessment

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

## Cost

This project is **completely free** to use:

- **faster-whisper**: Runs locally, no API costs
- **Gemini API**: Free tier (15 requests/min, 1M tokens/month)
- **SQLite**: Free, no setup required
- **Next.js**: Free, open-source

## Project Structure

```
AI-Interviewer/
├── backend/
│   └── app/
│       ├── routers/       # API endpoints
│       ├── services/      # Business logic
│       │   ├── speech_service.py     # Speech-to-text
│       │   ├── evaluation_service.py # AI evaluation
│       │   └── risk_engine.py        # Proctoring
│       ├── models/        # Database models
│       └── core/         # Config, security
├── frontend/
│   └── src/
│       └── app/
│           ├── recruiter/      # Recruiter pages
│           └── interview/      # Candidate pages
└── README.md
```

## License

MIT License - Free to use for any purpose.
