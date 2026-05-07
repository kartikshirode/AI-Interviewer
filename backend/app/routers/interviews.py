import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.models import Candidate, Interview, Question, Recruiter, Topic
from app.models.schemas import (
    CandidateSummary,
    InterviewCreate,
    InterviewResponse,
    QuestionCreateBody,
    QuestionResponse,
)
from app.routers.auth import get_current_recruiter

SAMPLE_QUESTIONS = {
    "Python": [
        "Explain the difference between list and tuple in Python.",
        "What are decorators in Python and how would you create one?",
        "Describe the Global Interpreter Lock (GIL) in Python.",
        "How does list comprehension work in Python?",
        "What is the difference between shallow and deep copy?",
    ],
    "Machine Learning": [
        "Explain the difference between supervised and unsupervised learning.",
        "What is overfitting and how can you prevent it?",
        "Describe the bias-variance tradeoff.",
        "What is gradient descent and how does it work?",
        "Explain the working of random forests.",
    ],
    "NLP": [
        "What is the difference between lemmatization and stemming?",
        "Explain TF-IDF and its importance in NLP.",
        "What are word embeddings and how do they work?",
        "Describe the transformer architecture.",
        "What is the purpose of attention mechanisms in NLP?",
    ],
    "Statistics": [
        "Explain the difference between mean, median, and mode.",
        "What is p-value and how do you interpret it?",
        "Describe the Central Limit Theorem.",
        "What is the difference between correlation and causation?",
        "Explain hypothesis testing and null hypothesis.",
    ],
    "SQL": [
        "What is the difference between INNER JOIN and LEFT JOIN?",
        "Explain the concept of primary key and foreign key.",
        "What are SQL indexes and how do they improve performance?",
        "Describe the difference between WHERE and HAVING clauses.",
        "What is normalization in databases?",
    ],
    "Data Structures": [
        "Explain the difference between array and linked list.",
        "What is the time complexity of common operations in a hash table?",
        "Describe the difference between stack and queue.",
        "Explain binary search tree traversal methods.",
        "What is Big O notation and why is it important?",
    ],
    "Deep Learning": [
        "Explain the concept of backpropagation.",
        "What is the difference between CNN and RNN?",
        "Describe how dropout helps in neural networks.",
        "What are activation functions? Name a few commonly used ones.",
        "Explain the vanishing gradient problem.",
    ],
    "System Design": [
        "How would you design a URL shortening service like bit.ly?",
        "Design a distributed caching system.",
        "What is load balancing and what algorithms are commonly used?",
        "Explain the CAP theorem.",
        "How would you design a real-time chat application?",
    ],
}

router = APIRouter(prefix="/interviews", tags=["Interviews"])


def _distribute_question_count(total: int, buckets: int) -> List[int]:
    """Distribute `total` questions across `buckets` topics as evenly as
    possible. Earlier buckets get the remainder."""
    if buckets <= 0 or total <= 0:
        return []
    base = total // buckets
    remainder = total % buckets
    return [base + (1 if i < remainder else 0) for i in range(buckets)]


@router.post("/", response_model=InterviewResponse, status_code=status.HTTP_201_CREATED)
def create_interview(
    interview: InterviewCreate,
    db: Session = Depends(get_db),
    recruiter: Recruiter = Depends(get_current_recruiter),
):
    interview_link = str(uuid.uuid4())
    db_interview = Interview(
        recruiter_id=recruiter.id,
        role=interview.role,
        difficulty=interview.difficulty,
        num_questions=interview.num_questions,
        interview_link=interview_link,
        status="active",
    )
    db.add(db_interview)
    db.commit()
    db.refresh(db_interview)

    questions_to_create: List[Question] = []

    # Resolve selected topics in the same order the recruiter sent them so the
    # distribution is deterministic.
    selected_topics: List[Topic] = []
    for topic_id in interview.topics:
        topic = db.query(Topic).filter(Topic.id == topic_id).first()
        if topic:
            selected_topics.append(topic)

    if selected_topics:
        per_topic_counts = _distribute_question_count(
            interview.num_questions, len(selected_topics)
        )
        for topic, take in zip(selected_topics, per_topic_counts):
            if take <= 0:
                continue
            sample_pool = SAMPLE_QUESTIONS.get(str(topic.name), [])
            for q_text in sample_pool[:take]:
                questions_to_create.append(
                    Question(
                        interview_id=db_interview.id,
                        topic_id=topic.id,
                        question_text=q_text,
                        source="system",
                    )
                )

    for q_text in interview.custom_questions:
        questions_to_create.append(
            Question(
                interview_id=db_interview.id,
                question_text=q_text,
                source="recruiter",
            )
        )

    for q in questions_to_create:
        db.add(q)
    db.commit()

    return db_interview


@router.get("/", response_model=List[InterviewResponse])
def list_interviews(
    db: Session = Depends(get_db),
    recruiter: Recruiter = Depends(get_current_recruiter),
):
    return (
        db.query(Interview).filter(Interview.recruiter_id == recruiter.id).all()
    )


@router.get("/{interview_id}", response_model=InterviewResponse)
def get_interview(
    interview_id: int,
    db: Session = Depends(get_db),
    recruiter: Recruiter = Depends(get_current_recruiter),
):
    interview = (
        db.query(Interview)
        .filter(Interview.id == interview_id, Interview.recruiter_id == recruiter.id)
        .first()
    )
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")
    return interview


@router.delete("/{interview_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_interview(
    interview_id: int,
    db: Session = Depends(get_db),
    recruiter: Recruiter = Depends(get_current_recruiter),
):
    interview = (
        db.query(Interview)
        .filter(Interview.id == interview_id, Interview.recruiter_id == recruiter.id)
        .first()
    )
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")

    db.delete(interview)
    db.commit()
    return None


@router.get("/{interview_id}/questions", response_model=List[QuestionResponse])
def get_interview_questions(
    interview_id: int,
    db: Session = Depends(get_db),
    recruiter: Recruiter = Depends(get_current_recruiter),
):
    interview = (
        db.query(Interview)
        .filter(Interview.id == interview_id, Interview.recruiter_id == recruiter.id)
        .first()
    )
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")

    return db.query(Question).filter(Question.interview_id == interview_id).all()


@router.post(
    "/{interview_id}/questions",
    response_model=QuestionResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_custom_question(
    interview_id: int,
    body: QuestionCreateBody,
    db: Session = Depends(get_db),
    recruiter: Recruiter = Depends(get_current_recruiter),
):
    interview = (
        db.query(Interview)
        .filter(Interview.id == interview_id, Interview.recruiter_id == recruiter.id)
        .first()
    )
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")

    db_question = Question(
        interview_id=interview_id,
        question_text=body.question_text,
        source="recruiter",
    )
    db.add(db_question)
    db.commit()
    db.refresh(db_question)
    return db_question


@router.get("/sample-questions/{topic_id}")
def get_sample_questions_for_topic(
    topic_id: int,
    db: Session = Depends(get_db),
    recruiter: Recruiter = Depends(get_current_recruiter),
):
    """Preview the canned questions that get attached when a topic is
    selected during interview creation. Returns an empty list if the topic
    has no preset bank."""
    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    questions = SAMPLE_QUESTIONS.get(str(topic.name), [])
    return {
        "topic_id": topic.id,
        "topic_name": topic.name,
        "questions": questions,
    }


@router.get("/{interview_id}/candidates", response_model=List[CandidateSummary])
def get_interview_candidates(
    interview_id: int,
    db: Session = Depends(get_db),
    recruiter: Recruiter = Depends(get_current_recruiter),
):
    interview = (
        db.query(Interview)
        .filter(Interview.id == interview_id, Interview.recruiter_id == recruiter.id)
        .first()
    )
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")

    return db.query(Candidate).filter(Candidate.interview_id == interview_id).all()
