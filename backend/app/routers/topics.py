from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.core.database import get_db
from app.models.models import Recruiter, Topic
from app.models.schemas import TopicBase, TopicResponse
from app.routers.auth import get_current_recruiter
from app.services.skills import GENERAL_SKILLS, normalize_skills_list

router = APIRouter(prefix="/topics", tags=["Topics"])


@router.post("/", response_model=TopicResponse, status_code=status.HTTP_201_CREATED)
def create_topic(
    topic: TopicBase,
    db: Session = Depends(get_db),
    recruiter: Recruiter = Depends(get_current_recruiter),
):
    existing = db.query(Topic).filter(Topic.name == topic.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Topic already exists")

    db_topic = Topic(
        name=topic.name,
        description=topic.description,
        skills=normalize_skills_list(topic.skills),
    )
    db.add(db_topic)
    db.commit()
    db.refresh(db_topic)
    return db_topic


@router.get("/general-skills", response_model=List[str])
def list_general_skills():
    """Soft skills offered alongside every topic in the create-interview UI.
    Returned as a flat list because the frontend treats them identically
    regardless of which topic is selected."""
    return GENERAL_SKILLS


@router.get("/", response_model=List[TopicResponse])
def list_topics(db: Session = Depends(get_db)):
    return db.query(Topic).all()


@router.get("/{topic_id}", response_model=TopicResponse)
def get_topic(topic_id: int, db: Session = Depends(get_db)):
    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    return topic
