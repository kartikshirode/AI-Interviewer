from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import init_db, SessionLocal
from app.models.models import Topic
from app.routers import auth, interviews, topics, candidate, video, voice

DEFAULT_TOPICS = [
    {"name": "Python", "description": "Python programming language fundamentals and advanced concepts"},
    {"name": "Machine Learning", "description": "ML algorithms, models, and techniques"},
    {"name": "NLP", "description": "Natural Language Processing concepts and tools"},
    {"name": "Statistics", "description": "Probability, statistics, and data analysis"},
    {"name": "SQL", "description": "Database queries and SQL programming"},
    {"name": "Data Structures", "description": "Arrays, linked lists, trees, graphs, and algorithms"},
    {"name": "Deep Learning", "description": "Neural networks, CNNs, RNNs, and transformers"},
    {"name": "System Design", "description": "Scalable system architecture and design patterns"},
]

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix=settings.API_PREFIX)
app.include_router(interviews.router, prefix=settings.API_PREFIX)
app.include_router(topics.router, prefix=settings.API_PREFIX)
app.include_router(candidate.router, prefix=settings.API_PREFIX)
app.include_router(video.router, prefix=settings.API_PREFIX)
app.include_router(voice.router, prefix=settings.API_PREFIX)

@app.on_event("startup")
def on_startup():
    init_db()
    db = SessionLocal()
    try:
        existing = db.query(Topic).first()
        if not existing:
            for topic_data in DEFAULT_TOPICS:
                db.add(Topic(**topic_data))
            db.commit()
    finally:
        db.close()

@app.get("/")
def root():
    return {"message": "AI Interviewer API", "version": settings.VERSION}

@app.get("/health")
def health_check():
    return {"status": "healthy"}
