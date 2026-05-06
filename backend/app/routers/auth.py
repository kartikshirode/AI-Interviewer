from fastapi import APIRouter, Depends, HTTPException, Header, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from datetime import timedelta
from typing import Optional

from app.core.database import get_db
from app.core.security import (
    verify_password,
    dummy_verify_password,
    get_password_hash,
    create_access_token,
    decode_token,
    decode_candidate_token,
)
from app.core.config import settings
from app.models.models import Recruiter, Candidate
from app.models.schemas import RecruiterCreate, RecruiterResponse, LoginRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["Authentication"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_PREFIX}/auth/login")


@router.post("/signup", response_model=RecruiterResponse, status_code=status.HTTP_201_CREATED)
def signup(recruiter: RecruiterCreate, db: Session = Depends(get_db)):
    existing = db.query(Recruiter).filter(Recruiter.email == recruiter.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    db_recruiter = Recruiter(
        email=recruiter.email,
        hashed_password=get_password_hash(recruiter.password),
        full_name=recruiter.full_name,
        company=recruiter.company,
    )
    db.add(db_recruiter)
    db.commit()
    db.refresh(db_recruiter)
    return db_recruiter


@router.post("/login", response_model=TokenResponse)
def login(credentials: LoginRequest, db: Session = Depends(get_db)):
    recruiter = db.query(Recruiter).filter(Recruiter.email == credentials.email).first()

    # Always run a bcrypt operation to mitigate user-existence timing leaks.
    if not recruiter:
        dummy_verify_password(credentials.password)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not verify_password(credentials.password, recruiter.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    access_token = create_access_token(
        data={"sub": recruiter.email, "id": recruiter.id},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return {"access_token": access_token, "token_type": "bearer"}


def get_current_recruiter(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> Recruiter:
    payload = decode_token(token)
    if not payload or "id" not in payload:
        raise HTTPException(status_code=401, detail="Invalid token")

    recruiter = db.query(Recruiter).filter(Recruiter.id == payload.get("id")).first()
    if not recruiter:
        raise HTTPException(status_code=401, detail="Invalid token")
    return recruiter


def get_current_candidate(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> Candidate:
    """Authenticate a candidate via the session token issued at registration.
    Token is sent in the standard `Authorization: Bearer <jwt>` header."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing candidate token")

    token = authorization.split(" ", 1)[1].strip()
    payload = decode_candidate_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid candidate token")

    candidate_id = payload.get("candidate_id")
    interview_id = payload.get("interview_id")
    if not candidate_id or not interview_id:
        raise HTTPException(status_code=401, detail="Malformed candidate token")

    candidate = (
        db.query(Candidate)
        .filter(Candidate.id == candidate_id, Candidate.interview_id == interview_id)
        .first()
    )
    if not candidate:
        raise HTTPException(status_code=401, detail="Candidate not found")
    return candidate
