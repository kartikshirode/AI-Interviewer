from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy import insert as sa_insert

from app.core.config import settings
from app.core.database import init_db, SessionLocal, engine
from app.models.models import Topic
from app.routers import auth, interviews, topics, candidate, video


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


def _seed_default_topics() -> None:
    """Idempotently seed the default topics. Uses INSERT OR IGNORE on SQLite,
    falls back to per-row checks on other dialects so that concurrent reload
    workers do not race each other into IntegrityErrors."""
    db = SessionLocal()
    try:
        dialect = engine.dialect.name
        if dialect == "sqlite":
            stmt = sqlite_insert(Topic).values(DEFAULT_TOPICS).prefix_with("OR IGNORE")
            db.execute(stmt)
            db.commit()
            return

        for topic_data in DEFAULT_TOPICS:
            existing = db.query(Topic).filter(Topic.name == topic_data["name"]).first()
            if not existing:
                db.add(Topic(**topic_data))
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    _seed_default_topics()
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix=settings.API_PREFIX)
app.include_router(interviews.router, prefix=settings.API_PREFIX)
app.include_router(topics.router, prefix=settings.API_PREFIX)
app.include_router(candidate.router, prefix=settings.API_PREFIX)
app.include_router(video.router, prefix=settings.API_PREFIX)


@app.get("/")
def root():
    return {"message": "AI Interviewer API", "version": settings.VERSION}


@app.get("/health")
def health_check():
    return {"status": "healthy"}
