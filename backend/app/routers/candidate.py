from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List, Optional
import os
import uuid
from pathlib import Path

from app.core.database import get_db
from app.models.models import Interview, Question, Candidate, Answer
from app.models.schemas import CandidateCreate, CandidateResponse, QuestionResponse

UPLOAD_DIR = Path("backend/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

router = APIRouter(prefix="/candidate", tags=["Candidate Interview"])

@router.get("/interview/{interview_link}")
def get_interview_by_link(interview_link: str, db: Session = Depends(get_db)):
    interview = db.query(Interview).filter(Interview.interview_link == interview_link).first()
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")
    
    return {
        "id": interview.id,
        "role": interview.role,
        "difficulty": interview.difficulty,
        "num_questions": interview.num_questions,
        "status": interview.status
    }

@router.post("/interview/{interview_id}/register", response_model=CandidateResponse, status_code=status.HTTP_201_CREATED)
def register_candidate(interview_id: int, candidate: CandidateCreate, db: Session = Depends(get_db)):
    interview = db.query(Interview).filter(Interview.id == interview_id).first()
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")
    
    db_candidate = Candidate(
        interview_id=interview_id,
        name=candidate.name,
        email=candidate.email,
        status="registered"
    )
    db.add(db_candidate)
    db.commit()
    db.refresh(db_candidate)
    return db_candidate

@router.get("/interview/{interview_id}/questions", response_model=List[QuestionResponse])
def get_interview_questions_for_candidate(interview_id: int, db: Session = Depends(get_db)):
    interview = db.query(Interview).filter(Interview.id == interview_id).first()
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")
    
    questions = db.query(Question).filter(Question.interview_id == interview_id).all()
    return questions

@router.post("/interview/{interview_id}/start")
def start_interview(interview_id: int, candidate_id: int, db: Session = Depends(get_db)):
    candidate = db.query(Candidate).filter(
        Candidate.id == candidate_id,
        Candidate.interview_id == interview_id
    ).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    
    candidate.status = "in_progress"
    db.commit()
    return {"status": "started", "candidate_id": candidate_id}

@router.post("/answer")
async def submit_answer(
    candidate_id: int = Form(...),
    question_id: int = Form(...),
    transcript: Optional[str] = Form(None),
    video: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db)
):
    candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    
    video_path = None
    if video:
        file_ext = os.path.splitext(video.filename)[1]
        file_name = f"{uuid.uuid4()}{file_ext}"
        file_path = UPLOAD_DIR / file_name
        
        content = await video.read()
        with open(file_path, "wb") as f:
            f.write(content)
        
        video_path = str(file_path)
    
    existing_answer = db.query(Answer).filter(
        Answer.candidate_id == candidate_id,
        Answer.question_id == question_id
    ).first()
    
    if existing_answer:
        existing_answer.transcript = transcript
        if video_path:
            existing_answer.video_path = video_path
        db.commit()
        return existing_answer
    else:
        answer = Answer(
            candidate_id=candidate_id,
            question_id=question_id,
            transcript=transcript,
            video_path=video_path
        )
        db.add(answer)
        db.commit()
        db.refresh(answer)
        return answer

@router.post("/interview/{interview_id}/complete")
def complete_interview(interview_id: int, candidate_id: int, db: Session = Depends(get_db)):
    candidate = db.query(Candidate).filter(
        Candidate.id == candidate_id,
        Candidate.interview_id == interview_id
    ).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    
    candidate.status = "completed"
    db.commit()
    return {"status": "completed", "candidate_id": candidate_id}

@router.post("/answer/{answer_id}/transcribe")
def transcribe_answer(answer_id: int, db: Session = Depends(get_db)):
    """Transcribe video/audio for an answer"""
    from app.services.speech_service import speech_service
    
    answer = db.query(Answer).filter(Answer.id == answer_id).first()
    if not answer:
        raise HTTPException(status_code=404, detail="Answer not found")
    
    if not answer.video_path or not os.path.exists(answer.video_path):
        return {"transcript": answer.transcript or "", "message": "No video file to transcribe"}
    
    try:
        transcript = speech_service.transcribe_video(answer.video_path)
        answer.transcript = transcript
        db.commit()
        return {"transcript": transcript, "status": "success"}
    except Exception as e:
        return {"transcript": answer.transcript or "", "error": str(e)}

@router.post("/candidate/{candidate_id}/transcribe-all")
def transcribe_all_answers(candidate_id: int, db: Session = Depends(get_db)):
    """Transcribe all answers for a candidate"""
    from app.services.speech_service import speech_service
    
    candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    
    answers = db.query(Answer).filter(Answer.candidate_id == candidate_id).all()
    results = []
    
    for answer in answers:
        if answer.video_path and os.path.exists(answer.video_path):
            try:
                transcript = speech_service.transcribe_video(answer.video_path)
                answer.transcript = transcript
                db.commit()
                results.append({"answer_id": answer.id, "transcript": transcript, "status": "success"})
            except Exception as e:
                results.append({"answer_id": answer.id, "error": str(e), "status": "failed"})
    
    return {"results": results}

@router.post("/answer/{answer_id}/evaluate")
def evaluate_answer(answer_id: int, db: Session = Depends(get_db)):
    """Evaluate a single answer"""
    from app.services.evaluation_service import evaluation_service
    
    answer = db.query(Answer).filter(Answer.id == answer_id).first()
    if not answer:
        raise HTTPException(status_code=404, detail="Answer not found")
    
    if not answer.transcript:
        return {"error": "No transcript available for evaluation"}
    
    question = db.query(Question).filter(Question.id == answer.question_id).first()
    topic = None
    if question and question.topic_id:
        from app.models.models import Topic
        topic_obj = db.query(Topic).filter(Topic.id == question.topic_id).first()
        topic = topic_obj.name if topic_obj else None
    
    interview = db.query(Interview).filter(Interview.id == answer.candidate.interview_id).first()
    difficulty = interview.difficulty if interview else "medium"
    
    evaluation = evaluation_service.evaluate_answer(
        question=question.question_text if question else "",
        transcript=answer.transcript,
        difficulty=difficulty,
        topic=topic
    )
    
    answer.correctness = evaluation["correctness"]
    answer.clarity = evaluation["clarity"]
    answer.depth = evaluation["depth"]
    db.commit()
    
    return evaluation

@router.post("/candidate/{candidate_id}/evaluate")
def evaluate_candidate(candidate_id: int, db: Session = Depends(get_db)):
    """Evaluate all answers for a candidate and calculate final score"""
    from app.services.evaluation_service import evaluation_service
    
    candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    
    answers = db.query(Answer).filter(Answer.candidate_id == candidate_id).all()
    
    if not answers:
        return {"error": "No answers to evaluate"}
    
    answer_evaluations = []
    for answer in answers:
        if not answer.transcript:
            continue
            
        question = db.query(Question).filter(Question.id == answer.question_id).first()
        topic = None
        if question and question.topic_id:
            from app.models.models import Topic
            topic_obj = db.query(Topic).filter(Topic.id == question.topic_id).first()
            topic = topic_obj.name if topic_obj else None
        
        interview = db.query(Interview).filter(Interview.id == answer.candidate.interview_id).first()
        difficulty = interview.difficulty if interview else "medium"
        
        evaluation = evaluation_service.evaluate_answer(
            question=question.question_text if question else "",
            transcript=answer.transcript,
            difficulty=difficulty,
            topic=topic
        )
        
        answer.correctness = evaluation["correctness"]
        answer.clarity = evaluation["clarity"]
        answer.depth = evaluation["depth"]
        db.commit()
        
        answer_evaluations.append(evaluation)
    
    all_transcripts = "\n\n".join([a.transcript for a in answers if a.transcript])
    comm_eval = evaluation_service.evaluate_communication(all_transcripts, len(answers))
    
    final_scores = evaluation_service.calculate_final_score(answer_evaluations, comm_eval["communication_score"])
    
    candidate.final_score = final_scores["final_score"]
    candidate.communication_score = comm_eval["communication_score"]
    db.commit()
    
    return {
        "final_score": final_scores["final_score"],
        "technical_score": final_scores["technical_score"],
        "communication_score": final_scores["communication_score"],
        "answer_evaluations": answer_evaluations,
        "communication_evaluation": comm_eval
    }

@router.post("/candidate/{candidate_id}/proctoring")
def save_proctoring_data(candidate_id: int, db: Session = Depends(get_db)):
    """Save proctoring events and calculate risk score"""
    from app.models.schemas import ProctoringData
    
    candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    
    return {"status": "received", "candidate_id": candidate_id}

@router.post("/candidate/{candidate_id}/proctoring/report")
def get_proctoring_report(candidate_id: int, db: Session = Depends(get_db)):
    """Get proctoring report for a candidate"""
    from app.services.risk_engine import RiskEngine
    
    candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    
    answers = db.query(Answer).filter(Answer.candidate_id == candidate_id).all()
    
    tab_switch_count = sum(1 for a in answers if a.is_flagged and a.flag_reason == 'tab_switch')
    clipboard_count = sum(1 for a in answers if a.is_flagged and a.flag_reason == 'clipboard')
    
    risk_result = RiskEngine.calculate_combined_risk(
        tab_switches=tab_switch_count,
        clipboard_pastes=clipboard_count
    )
    
    candidate.cheating_risk = risk_result["risk_level"]
    db.commit()
    
    return risk_result

@router.get("/candidate/{candidate_id}/report")
def get_candidate_report(candidate_id: int, db: Session = Depends(get_db)):
    """Generate comprehensive candidate report"""
    from app.models.models import Question, Interview, Topic
    
    candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    
    interview = db.query(Interview).filter(Interview.id == candidate.interview_id).first()
    answers = db.query(Answer).filter(Answer.candidate_id == candidate_id).all()
    
    question_evaluations = []
    topic_scores = {}
    
    for answer in answers:
        question = db.query(Question).filter(Question.id == answer.question_id).first()
        topic = None
        if question and question.topic_id:
            topic_obj = db.query(Topic).filter(Topic.id == question.topic_id).first()
            topic = topic_obj.name if topic_obj else None
        
        question_evaluations.append({
            "question_id": question.id if question else None,
            "question_text": question.question_text if question else "",
            "topic": topic,
            "transcript": answer.transcript,
            "video_path": answer.video_path,
            "correctness": answer.correctness,
            "clarity": answer.clarity,
            "depth": answer.depth,
            "is_flagged": answer.is_flagged,
            "flag_reason": answer.flag_reason
        })
        
        if topic:
            if topic not in topic_scores:
                topic_scores[topic] = {"total": 0, "count": 0}
            if answer.correctness:
                topic_scores[topic]["total"] += answer.correctness
                topic_scores[topic]["count"] += 1
    
    topic_averages = {}
    for topic, data in topic_scores.items():
        topic_averages[topic] = round(data["total"] / data["count"], 2) if data["count"] > 0 else 0
    
    return {
        "candidate": {
            "id": candidate.id,
            "name": candidate.name,
            "email": candidate.email,
            "status": candidate.status
        },
        "interview": {
            "id": interview.id if interview else None,
            "role": interview.role if interview else "",
            "difficulty": interview.difficulty if interview else "",
            "status": interview.status if interview else ""
        },
        "scores": {
            "final_score": candidate.final_score,
            "technical_score": sum(a.correctness or 0 for a in answers) / len(answers) if answers else 0,
            "communication_score": candidate.communication_score,
            "cheating_risk": candidate.cheating_risk
        },
        "topic_scores": topic_averages,
        "question_evaluations": question_evaluations,
        "total_questions": len(answers),
        "answered_questions": len([a for a in answers if a.transcript])
    }
