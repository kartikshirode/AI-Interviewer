import logging
import random
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.models import (
    Candidate,
    Interview,
    Question,
    QuestionBank,
    Recruiter,
    Topic,
)
from app.models.schemas import (
    CandidateSummary,
    InterviewCreate,
    InterviewResponse,
    QuestionCreateBody,
    QuestionResponse,
)
from app.routers.auth import get_current_recruiter
from app.services.question_generator import QuestionGenerator
from app.services.skills import normalize_skills_key, normalize_skills_list

logger = logging.getLogger(__name__)

# Question bank stratified by difficulty. The bank for the chosen difficulty
# is the only one used at interview-creation time; `medium` is also the
# fallback for unknown / legacy difficulty values.
SAMPLE_QUESTIONS_BY_DIFFICULTY: dict[str, dict[str, list[str]]] = {
    "Python": {
        "easy": [
            "What is the difference between a list and a tuple in Python?",
            "How do you read a file line by line in Python?",
            "What does the `len()` function return for a dictionary?",
            "How do you remove duplicates from a list?",
            "What is the difference between `==` and `is` in Python?",
        ],
        "medium": [
            "Explain the difference between list and tuple in Python.",
            "What are decorators in Python and how would you create one?",
            "Describe the Global Interpreter Lock (GIL) in Python.",
            "How does list comprehension work in Python?",
            "What is the difference between shallow and deep copy?",
        ],
        "hard": [
            "Explain how the GIL affects multithreaded CPU-bound code, and how you'd work around it.",
            "Walk through how Python's garbage collector handles reference cycles.",
            "Implement a metaclass and describe a real situation where it's the right tool.",
            "How does `asyncio` schedule coroutines under the hood, and what makes a task block the event loop?",
            "Describe the descriptor protocol and how `@property` is implemented in terms of it.",
        ],
    },
    "Machine Learning": {
        "easy": [
            "What's the difference between classification and regression?",
            "Give an example of a supervised vs. an unsupervised problem.",
            "What is a training set, validation set, and test set used for?",
            "What does it mean if a model is overfitting?",
            "Name two common evaluation metrics for a classification model.",
        ],
        "medium": [
            "Explain the difference between supervised and unsupervised learning.",
            "What is overfitting and how can you prevent it?",
            "Describe the bias-variance tradeoff.",
            "What is gradient descent and how does it work?",
            "Explain the working of random forests.",
        ],
        "hard": [
            "Derive the gradient of cross-entropy loss with softmax and explain why the math simplifies the way it does.",
            "Compare L1 and L2 regularization at the level of their effect on the loss surface and the resulting weights.",
            "How would you debug a model that performs well on validation but poorly in production?",
            "Explain the EM algorithm and walk through one iteration on a Gaussian mixture model.",
            "Design an evaluation protocol for a recommender system where labels are implicit feedback.",
        ],
    },
    "NLP": {
        "easy": [
            "What is tokenization?",
            "Give an example of a stop word and explain why it might be removed.",
            "What is the difference between a word and a token?",
            "Why might you lowercase text before processing it?",
            "What is named entity recognition?",
        ],
        "medium": [
            "What is the difference between lemmatization and stemming?",
            "Explain TF-IDF and its importance in NLP.",
            "What are word embeddings and how do they work?",
            "Describe the transformer architecture.",
            "What is the purpose of attention mechanisms in NLP?",
        ],
        "hard": [
            "Explain self-attention with key, query, and value matrices, and why scaling by sqrt(d_k) matters.",
            "Compare BPE and WordPiece tokenization and the tradeoffs each makes.",
            "How would you fine-tune a pre-trained language model for a low-resource domain without catastrophic forgetting?",
            "Walk through how an encoder-decoder transformer handles a translation task at training time vs. inference time.",
            "Describe a situation where retrieval-augmented generation outperforms a larger fine-tuned model and why.",
        ],
    },
    "Statistics": {
        "easy": [
            "What is the mean of [2, 4, 4, 4, 5, 5, 7, 9]?",
            "What is the difference between a population and a sample?",
            "Give an example of a discrete and a continuous random variable.",
            "What does standard deviation tell you about a dataset?",
            "If you flip a fair coin twice, what is the probability of two heads?",
        ],
        "medium": [
            "Explain the difference between mean, median, and mode.",
            "What is p-value and how do you interpret it?",
            "Describe the Central Limit Theorem.",
            "What is the difference between correlation and causation?",
            "Explain hypothesis testing and null hypothesis.",
        ],
        "hard": [
            "When does the Central Limit Theorem fail to apply, and what would you do instead?",
            "Explain the difference between Type I and Type II errors and how power analysis informs sample size.",
            "Walk through how you'd design and analyse an A/B test where the metric is heavy-tailed.",
            "Compare frequentist confidence intervals with Bayesian credible intervals.",
            "Explain Simpson's paradox with a concrete example and how stratification resolves it.",
        ],
    },
    "SQL": {
        "easy": [
            "Write a query to select all rows from a table named `users`.",
            "How do you count the number of rows in a table?",
            "What does the `DISTINCT` keyword do?",
            "What is the difference between `WHERE` and `ORDER BY`?",
            "How do you sort results in descending order?",
        ],
        "medium": [
            "What is the difference between INNER JOIN and LEFT JOIN?",
            "Explain the concept of primary key and foreign key.",
            "What are SQL indexes and how do they improve performance?",
            "Describe the difference between WHERE and HAVING clauses.",
            "What is normalization in databases?",
        ],
        "hard": [
            "Walk through what happens when a query uses a non-sargable predicate and how the optimizer handles it.",
            "Compare clustered vs. non-clustered indexes and when each makes sense.",
            "Explain transaction isolation levels and the anomalies each one prevents.",
            "Write a query using window functions to find the top 3 earners per department, and explain the alternatives.",
            "Describe how you'd diagnose a query that runs fast in dev and slow in production despite identical schemas.",
        ],
    },
    "Data Structures": {
        "easy": [
            "What is an array?",
            "What's the difference between a stack and a queue?",
            "What does FIFO stand for?",
            "What is the time complexity of looking up an element by index in an array?",
            "Name one situation where you'd prefer a linked list over an array.",
        ],
        "medium": [
            "Explain the difference between array and linked list.",
            "What is the time complexity of common operations in a hash table?",
            "Describe the difference between stack and queue.",
            "Explain binary search tree traversal methods.",
            "What is Big O notation and why is it important?",
        ],
        "hard": [
            "Compare a B-tree and a B+ tree and describe why databases prefer one for indexes.",
            "Implement an LRU cache with O(1) get and put, and explain each data-structure choice.",
            "Walk through the amortized analysis of a dynamic array's append operation.",
            "When would you reach for a Fenwick tree vs. a segment tree, and what's the tradeoff?",
            "Describe how a skip list achieves logarithmic operations probabilistically and where it shines vs. a balanced BST.",
        ],
    },
    "Deep Learning": {
        "easy": [
            "What is a neuron in a neural network?",
            "What does an activation function do?",
            "Name one common activation function.",
            "What is a loss function used for?",
            "Why do we split data into training and test sets?",
        ],
        "medium": [
            "Explain the concept of backpropagation.",
            "What is the difference between CNN and RNN?",
            "Describe how dropout helps in neural networks.",
            "What are activation functions? Name a few commonly used ones.",
            "Explain the vanishing gradient problem.",
        ],
        "hard": [
            "Derive backpropagation through a single hidden layer with a sigmoid activation.",
            "Compare BatchNorm, LayerNorm, and GroupNorm and the situations each is best suited to.",
            "Explain why residual connections enable training of very deep networks.",
            "Walk through how the Adam optimizer updates parameters and why it can outperform plain SGD.",
            "Describe the tradeoffs between transformer encoders and decoders for a sequence labeling task.",
        ],
    },
    "System Design": {
        "easy": [
            "What is a database, and what is it used for?",
            "What is the difference between a client and a server?",
            "What does an HTTP status code 200 mean?",
            "What is caching, in simple terms?",
            "Why might you use multiple servers for the same application?",
        ],
        "medium": [
            "How would you design a URL shortening service like bit.ly?",
            "Design a distributed caching system.",
            "What is load balancing and what algorithms are commonly used?",
            "Explain the CAP theorem.",
            "How would you design a real-time chat application?",
        ],
        "hard": [
            "Design a globally distributed rate limiter that survives a region outage.",
            "Walk through the storage and consistency tradeoffs you'd make for a feed system serving 100M users.",
            "Explain how you'd design a payment system that must be exactly-once at the user-visible level.",
            "Compare event sourcing with CRUD persistence for an order management service — when does each win?",
            "Describe how you'd evolve a monolith into services without a big-bang rewrite.",
        ],
    },
}

# Backwards-compatible alias used by existing call sites that don't yet pass
# a difficulty argument. Resolved to the medium bank.
SAMPLE_QUESTIONS = {topic: banks["medium"] for topic, banks in SAMPLE_QUESTIONS_BY_DIFFICULTY.items()}


def _static_bank(topic_name: str, difficulty: str) -> list[str]:
    """Static fallback bank used when Gemini is unavailable. `medium` is the
    fallback for unknown difficulty values; an unknown topic returns []."""
    banks = SAMPLE_QUESTIONS_BY_DIFFICULTY.get(str(topic_name))
    if not banks:
        return []
    return list(banks.get(difficulty) or banks.get("medium") or [])


# Module-level generator. Constructed lazily on first use so importing this
# module doesn't require a Gemini API key (e.g. during tests).
_generator: QuestionGenerator | None = None


def _get_generator() -> QuestionGenerator:
    global _generator
    if _generator is None:
        _generator = QuestionGenerator(fallback_provider=_static_bank)
    return _generator


def _persist_to_bank(
    db: Session,
    topic_name: str,
    difficulty: str,
    skills_key: str,
    skills_list: list[str],
    questions: list[str],
    source: str,
) -> None:
    """Insert generated questions into the QuestionBank, deduping on the
    (topic, difficulty, skills_key, question_text) unique constraint."""
    if not questions:
        return
    existing = {
        row.question_text
        for row in db.query(QuestionBank.question_text)
        .filter(
            QuestionBank.topic_name == topic_name,
            QuestionBank.difficulty == difficulty,
            QuestionBank.skills_key == skills_key,
        )
        .all()
    }
    for q in questions:
        if q in existing:
            continue
        try:
            db.add(
                QuestionBank(
                    topic_name=topic_name,
                    difficulty=difficulty,
                    skills_key=skills_key,
                    skills_json=skills_list,
                    question_text=q,
                    source=source,
                )
            )
            db.commit()
        except IntegrityError:
            # Lost a race with a concurrent writer — fine, the row exists.
            db.rollback()


def _resolve_questions(
    db: Session,
    topic_name: str,
    difficulty: str,
    skills: list[str],
    count: int = 5,
    force_refresh: bool = False,
) -> tuple[list[str], str]:
    """Resolve N questions for (topic, difficulty, skills) — DB bank first,
    Gemini on cache miss, static fallback if Gemini is unavailable.

    Returns (questions, source) where source ∈ {"bank-hit", "gemini",
    "static"}. The bank is the system-of-record for previously-generated
    questions; this function persists fresh generations on every miss so
    subsequent requests are token-free.
    """
    skills_list = normalize_skills_list(skills)
    skills_key = normalize_skills_key(skills_list)

    if not force_refresh:
        # Pull a small candidate pool ordered by least-used so the bank
        # spreads coverage. Random sample within the pool so different
        # interviews with the same key get different question subsets.
        pool = (
            db.query(QuestionBank)
            .filter(
                QuestionBank.topic_name == topic_name,
                QuestionBank.difficulty == difficulty,
                QuestionBank.skills_key == skills_key,
            )
            .order_by(QuestionBank.times_used.asc(), func.random())
            .limit(max(count * 3, count))
            .all()
        )
        if len(pool) >= count:
            chosen = random.sample(pool, count)
            now = datetime.now(timezone.utc)
            for row in chosen:
                row.times_used += 1
                row.last_used_at = now
            db.commit()
            return [row.question_text for row in chosen], "bank-hit"

    # Bank short or refresh forced → ask the generator.
    fresh, source = _get_generator().generate(
        topic_name=topic_name,
        difficulty=difficulty,
        skills=skills_list,
        count=count,
    )
    _persist_to_bank(
        db, topic_name, difficulty, skills_key, skills_list, fresh, source
    )
    return fresh[:count], source

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
    skills_list = normalize_skills_list(interview.skills)
    db_interview = Interview(
        recruiter_id=recruiter.id,
        role=interview.role,
        difficulty=interview.difficulty,
        num_questions=interview.num_questions,
        skills=skills_list,
        interview_link=interview_link,
        status="active",
    )
    db.add(db_interview)
    db.commit()
    db.refresh(db_interview)

    questions_to_create: List[Question] = []

    # Resolve selected catalog topics in order so distribution is deterministic.
    selected_topics: List[Topic] = []
    for topic_id in interview.topics:
        topic = db.query(Topic).filter(Topic.id == topic_id).first()
        if topic:
            selected_topics.append(topic)

    # A recruiter may pick "Other" → custom_topic. Treat it as one extra
    # topic-name slot in the distribution, with no Topic FK on the Question.
    custom_topic_name = (interview.custom_topic or "").strip()

    bucket_count = len(selected_topics) + (1 if custom_topic_name else 0)
    if bucket_count > 0:
        per_topic_counts = _distribute_question_count(
            interview.num_questions, bucket_count
        )

        for topic, take in zip(selected_topics, per_topic_counts):
            if take <= 0:
                continue
            sample_pool, _src = _resolve_questions(
                db,
                str(topic.name),
                interview.difficulty,
                skills_list,
                count=take,
            )
            for q_text in sample_pool[:take]:
                questions_to_create.append(
                    Question(
                        interview_id=db_interview.id,
                        topic_id=topic.id,
                        question_text=q_text,
                        source="system",
                    )
                )

        if custom_topic_name:
            take = per_topic_counts[len(selected_topics)]
            if take > 0:
                sample_pool, _src = _resolve_questions(
                    db,
                    custom_topic_name,
                    interview.difficulty,
                    skills_list,
                    count=take,
                )
                for q_text in sample_pool[:take]:
                    questions_to_create.append(
                        Question(
                            interview_id=db_interview.id,
                            topic_id=None,  # not in the curated catalog
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
    difficulty: str = "medium",
    count: int = 5,
    regenerate: bool = False,
    skills: List[str] = Query(default_factory=list),
    db: Session = Depends(get_db),
    recruiter: Recruiter = Depends(get_current_recruiter),
):
    """Preview the questions that will be attached for a curated topic.
    Bank-first lookup keyed on (topic, difficulty, skills); calls Gemini
    only when the bank is short or `regenerate=true`."""
    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    questions, source = _resolve_questions(
        db,
        str(topic.name),
        difficulty,
        skills,
        count=count,
        force_refresh=regenerate,
    )
    return {
        "topic_id": topic.id,
        "topic_name": topic.name,
        "difficulty": difficulty,
        "skills": skills,
        "source": source,
        "questions": questions,
    }


@router.get("/sample-questions/by-name/{topic_name}")
def get_sample_questions_for_custom_topic(
    topic_name: str,
    difficulty: str = "medium",
    count: int = 5,
    regenerate: bool = False,
    skills: List[str] = Query(default_factory=list),
    db: Session = Depends(get_db),
    recruiter: Recruiter = Depends(get_current_recruiter),
):
    """Preview endpoint for a custom ("Other") topic that isn't in the
    curated catalog. Same bank-first behavior as the by-id variant."""
    topic_name = topic_name.strip()
    if not topic_name:
        raise HTTPException(status_code=400, detail="topic_name is required")
    questions, source = _resolve_questions(
        db,
        topic_name,
        difficulty,
        skills,
        count=count,
        force_refresh=regenerate,
    )
    return {
        "topic_id": None,
        "topic_name": topic_name,
        "difficulty": difficulty,
        "skills": skills,
        "source": source,
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
