# AI Automated Interview System — Development Plan

## Project Goal

Build a **fully automated AI interview platform** where:

* Recruiters create interview templates based on **topics**
* Candidates attend an **AI-conducted interview**
* The system records **video, audio, and screen**
* AI evaluates answers automatically
* A **proctoring system detects cheating**
* Final **candidate report + score** is generated

No human intervention should be required during or after the interview.

---

# System Overview

Core subsystems:

1. Recruiter System
2. Interview Engine
3. Real-Time Media System
4. AI Evaluation Engine
5. AI Proctoring System
6. Reporting System

---

# Phase 1 — Project Foundation

## Objective

Create the base project structure.

## Tasks

### 1. Repository Setup

* Create GitHub repository
* Setup README
* Add `.gitignore`

Notes:

* Use **clear folder structure**
* Keep backend and frontend separate

---

### 2. Backend Initialization

Tasks:

* Setup FastAPI server
* Create base API routes
* Setup project structure

Example structure:

backend/
app/
main.py
routers/
services/
models/

Notes:

* Keep routes modular
* Separate services and controllers

---

### 3. Frontend Initialization

Tasks:

* Setup React or Next.js
* Create base layout
* Create routing system

Folders:

frontend/
pages/
components/
services/

Notes:

* Keep UI minimal initially
* Focus on functionality first

---

### 4. Database Setup

Tasks:

* Install PostgreSQL or SQLite
* Create ORM models
* Connect backend to database

Tables (initial):

* recruiters
* interviews
* topics
* questions

Notes:

* Start with **SQLite for development**
* Switch to PostgreSQL later

---

# Phase 2 — Recruiter Interview Configuration

## Objective

Allow recruiters to create interview templates.

---

## Tasks

### 1. Recruiter Authentication

Tasks:

* Signup API
* Login API
* JWT authentication

Notes:

* Password hashing
* Token based authentication

---

### 2. Interview Template Creation

Recruiter must define:

* role
* topics
* difficulty
* number of questions
* optional custom questions

Example:

Role: ML Intern
Topics: Python, NLP, ML
Questions: 6

---

### 3. Topics System

Topics represent **knowledge areas**.

Examples:

* Python
* Machine Learning
* NLP
* Statistics
* SQL

Database:

topics
id
name

Notes:

* Topics must be reusable across interviews

---

### 4. Custom Question Support

Recruiters can add questions.

Database:

questions
id
interview_id
question_text
source = recruiter

Notes:

* System questions and recruiter questions should both be supported

---

# Phase 3 — Candidate Interview System

## Objective

Allow candidate to attend interview.

---

## Tasks

### 1. Interview Link Generation

When recruiter creates interview:

* Generate interview URL
* Send link to candidate

Example:

/interview/{interview_id}

Notes:

* Links should expire after interview

---

### 2. Candidate Interview UI

UI elements:

* camera preview
* microphone
* screen share
* question display
* answer timer

Notes:

* Candidate must allow camera and microphone

---

### 3. Interview Controller

Responsible for:

* loading interview template
* selecting questions
* managing question order
* controlling timer

Flow:

Start interview
Load questions
Ask question
Record answer
Next question

Notes:

* Questions should appear **one at a time**

---

# Phase 4 — Real-Time Media System

## Objective

Capture video, audio, and screen.

---

## Tasks

### 1. Interview Room

Each interview creates a **media room**.

Participants:

* candidate
* AI interviewer

Notes:

* Only candidate video required

---

### 2. Webcam Capture

Tasks:

* request webcam permission
* start video stream
* record stream

Notes:

* video used for **proctoring**

---

### 3. Microphone Capture

Tasks:

* request mic permission
* capture audio
* stream audio

Notes:

* audio used for **speech transcription**

---

### 4. Screen Sharing

Tasks:

* request screen sharing permission
* record screen stream

Purpose:

* detect cheating
* detect tab switching
* detect external help

Notes:

* candidate must share **entire screen**

---

# Phase 5 — Speech Processing

## Objective

Convert spoken answers to text.

---

## Tasks

### 1. Extract Audio Stream

Steps:

* receive audio stream
* isolate candidate voice

Notes:

* store raw audio if needed

---

### 2. Speech-to-Text

Process:

Audio
→ speech recognition
→ transcript

Notes:

* transcription must be stored for evaluation

---

### 3. Transcript Storage

Database:

answers
id
candidate_id
question_id
transcript

Notes:

* transcripts used for scoring

---

# Phase 6 — AI Interview Evaluation

## Objective

Evaluate candidate answers automatically.

---

## Tasks

### 1. Answer Evaluation

Input:

* question
* transcript

Output:

* correctness
* clarity
* depth

Example output:

correctness: 8
clarity: 7
depth: 6

---

### 2. Score Aggregation

Combine all question scores.

Example:

Q1 = 7
Q2 = 8
Q3 = 6

Final Score = average

Notes:

* also generate **communication score**

---

# Phase 7 — AI Proctoring System

## Objective

Automatically detect cheating.

Signals monitored:

* eye movement
* multiple faces
* tab switching
* clipboard usage
* suspicious screen text

---

## Tasks

### 1. Eye Gaze Detection

Detect if candidate is looking away.

Logic:

if gaze != camera
increase gaze_away_counter

Notes:

* small deviations are normal

---

### 2. Multiple Face Detection

Detect if more than one person appears.

Logic:

faces_detected > 1
flag suspicious

---

### 3. Tab Switching Detection

Browser event monitoring.

Detect:

* tab change
* window blur

Notes:

* frequent switching indicates cheating

---

### 4. Clipboard Monitoring

Detect:

* copy
* paste

Notes:

* paste events may indicate external answers

---

### 5. Screen Text Detection

Capture screenshots periodically.

Steps:

screenshot
→ OCR
→ text extraction

Detect keywords:

* google
* chatgpt
* stackoverflow

Notes:

* flag if detected

---

# Phase 8 — Cheating Risk Engine

## Objective

Combine all signals.

Example scoring:

Tab Switch = 20
Gaze Away = 15
Multiple Face = 50
Clipboard = 10

Risk Score Range:

0–30 → Safe
30–60 → Warning
60–100 → Cheating

Notes:

* thresholds adjustable

---

# Phase 9 — Candidate Report System

## Objective

Generate final interview results.

Report includes:

* candidate name
* role
* topic scores
* communication score
* cheating risk

Example:

Candidate: Kartik
Technical Score: 7.8
Communication: 7.1
Cheating Risk: Low

---

# Phase 10 — Recruiter Results Dashboard

## Objective

Allow recruiter to view results.

---

## Features

### Candidate List

Display:

* candidate name
* score
* status

---

### Interview Playback

Recruiter can watch:

* webcam recording
* screen recording

---

### Report View

Recruiter sees:

* transcript
* scores
* cheating flags

---

# Development Order (Important)

Build in this order:

1. Backend foundation
2. Recruiter interview configuration
3. Candidate interview flow
4. Video/audio system
5. Speech transcription
6. AI answer evaluation
7. Proctoring system
8. Risk scoring
9. Reporting
10. Dashboard

---

# Notes

Important design principles:

* Keep modules independent
* Avoid tight coupling between systems
* Store all media for debugging
* Log suspicious behavior events

---

# Future Improvements

Possible future features:

* adaptive questioning
* AI follow-up questions
* behavioral analysis
* emotion detection
* coding interview support

---

# End Goal

Create a **fully automated AI interview system capable of screening candidates without human intervention.**
