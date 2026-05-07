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
    {
        "name": "Python",
        "description": "Python programming language fundamentals and advanced concepts",
        "skills": ["asyncio", "decorators", "typing", "performance", "OOP", "generators", "dataclasses"],
    },
    {
        "name": "Machine Learning",
        "description": "ML algorithms, models, and techniques",
        "skills": ["regression", "classification", "feature engineering", "regularization", "model evaluation", "ensembles", "cross-validation"],
    },
    {
        "name": "NLP",
        "description": "Natural Language Processing concepts and tools",
        "skills": ["tokenization", "embeddings", "transformers", "attention", "fine-tuning", "RAG", "named entity recognition"],
    },
    {
        "name": "Statistics",
        "description": "Probability, statistics, and data analysis",
        "skills": ["hypothesis testing", "Bayesian inference", "A/B testing", "distributions", "regression", "experimental design"],
    },
    {
        "name": "SQL",
        "description": "Database queries and SQL programming",
        "skills": ["joins", "indexes", "window functions", "transactions", "query optimization", "schema design", "CTEs"],
    },
    {
        "name": "Data Structures",
        "description": "Arrays, linked lists, trees, graphs, and algorithms",
        "skills": ["arrays", "trees", "graphs", "hash tables", "heaps", "dynamic programming", "complexity analysis"],
    },
    {
        "name": "Deep Learning",
        "description": "Neural networks, CNNs, RNNs, and transformers",
        "skills": ["backpropagation", "CNNs", "RNNs", "transformers", "optimization", "regularization", "transfer learning"],
    },
    {
        "name": "System Design",
        "description": "Scalable system architecture and design patterns",
        "skills": ["scalability", "caching", "load balancing", "consistency", "messaging queues", "database sharding", "high availability"],
    },
]


def _seed_default_topics() -> None:
    """Idempotently seed the default topics and refresh their skill catalog.

    Insert-or-ignore handles new rows; we then explicitly UPDATE each
    existing row's `skills` so curated skill lists picked up after the
    initial seed actually take effect (e.g. when adding the skills column
    in a backwards-compatible migration without dropping the DB)."""
    db = SessionLocal()
    try:
        dialect = engine.dialect.name
        if dialect == "sqlite":
            stmt = sqlite_insert(Topic).values(DEFAULT_TOPICS).prefix_with("OR IGNORE")
            db.execute(stmt)
        else:
            for topic_data in DEFAULT_TOPICS:
                existing = db.query(Topic).filter(Topic.name == topic_data["name"]).first()
                if not existing:
                    db.add(Topic(**topic_data))
            db.commit()

        # Refresh skills on existing seeded topics. Non-default custom topics
        # added by recruiters via POST /topics/ are left alone.
        for topic_data in DEFAULT_TOPICS:
            row = db.query(Topic).filter(Topic.name == topic_data["name"]).first()
            if row is not None:
                row.skills = topic_data.get("skills", [])
                if topic_data.get("description"):
                    row.description = topic_data["description"]
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
