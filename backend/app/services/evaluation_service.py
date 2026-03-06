import os
import json
from typing import Dict, Any, Optional
import openai

class EvaluationService:
    def __init__(self):
        self.client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))
    
    def evaluate_answer(
        self,
        question: str,
        transcript: str,
        difficulty: str = "medium",
        topic: Optional[str] = None
    ) -> Dict[str, Any]:
        """Evaluate a candidate's answer using OpenAI GPT"""
        
        system_prompt = f"""You are an expert technical interviewer evaluating a candidate's answer.
Evaluate the answer based on:
1. Correctness (0-10): Is the technical content accurate?
2. Clarity (0-10): Is the explanation clear and well-structured?
3. Depth (0-10): Does the answer show good understanding of the topic?

Difficulty level: {difficulty}
{f"Topic: {topic}" if topic else ""}

Provide a JSON response with:
{{
    "correctness": <score 0-10>,
    "clarity": <score 0-10>,
    "depth": <score 0-10>,
    "feedback": "<brief feedback on the answer>",
    "strengths": ["<strength 1>", "<strength 2>"],
    "areas_for_improvement": ["<area 1>", "<area 2>"]
}}

Be strict but fair in your evaluation."""

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Question: {question}\n\nAnswer: {transcript}"}
                ],
                temperature=0.3,
                max_tokens=500
            )
            
            result = json.loads(response.choices[0].message.content)
            return {
                "correctness": result.get("correctness", 5),
                "clarity": result.get("clarity", 5),
                "depth": result.get("depth", 5),
                "feedback": result.get("feedback", ""),
                "strengths": result.get("strengths", []),
                "areas_for_improvement": result.get("areas_for_improvement", [])
            }
        except Exception as e:
            print(f"Error evaluating answer: {e}")
            return {
                "correctness": 5,
                "clarity": 5,
                "depth": 5,
                "feedback": "Evaluation failed",
                "strengths": [],
                "areas_for_improvement": []
            }
    
    def evaluate_communication(
        self,
        transcript: str,
        question_count: int = 1
    ) -> Dict[str, Any]:
        """Evaluate communication skills based on all transcripts"""
        
        system_prompt = """You are evaluating a candidate's communication skills during an interview.
Analyze their overall communication based on:
1. Clarity of expression (0-10)
2. Professionalism (0-10)
3. Conciseness (0-10)
4. Confidence indicator (0-10)

Provide a JSON response:
{
    "communication_score": <average 0-10>,
    "clarity": <score 0-10>,
    "professionalism": <score 0-10>,
    "conciseness": <score 0-10>,
    "confidence": <score 0-10>,
    "overall_feedback": "<overall communication feedback>"
}"""

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Candidate's answers:\n\n{transcript}"}
                ],
                temperature=0.3,
                max_tokens=500
            )
            
            result = json.loads(response.choices[0].message.content)
            return {
                "communication_score": result.get("communication_score", 7),
                "clarity": result.get("clarity", 7),
                "professionalism": result.get("professionalism", 7),
                "conciseness": result.get("conciseness", 7),
                "confidence": result.get("confidence", 7),
                "overall_feedback": result.get("overall_feedback", "")
            }
        except Exception as e:
            print(f"Error evaluating communication: {e}")
            return {
                "communication_score": 7,
                "clarity": 7,
                "professionalism": 7,
                "conciseness": 7,
                "confidence": 7,
                "overall_feedback": "Communication evaluation failed"
            }
    
    def calculate_final_score(
        self,
        answers: list,
        communication_score: float
    ) -> Dict[str, Any]:
        """Calculate final aggregated score"""
        
        total_correctness = sum(a.get("correctness", 5) for a in answers)
        total_clarity = sum(a.get("clarity", 5) for a in answers)
        total_depth = sum(a.get("depth", 5) for a in answers)
        
        num_answers = len(answers) if answers else 1
        
        technical_score = (total_correctness + total_clarity + total_depth) / (3 * num_answers) * 10
        final_score = (technical_score * 0.7) + (communication_score * 0.3)
        
        return {
            "technical_score": round(technical_score, 2),
            "communication_score": round(communication_score, 2),
            "final_score": round(final_score, 2),
            "total_questions": num_answers,
            "average_correctness": round(total_correctness / num_answers, 2),
            "average_clarity": round(total_clarity / num_answers, 2),
            "average_depth": round(total_depth / num_answers, 2)
        }

evaluation_service = EvaluationService()
