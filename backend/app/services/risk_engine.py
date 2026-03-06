from typing import Dict, Any, List
from datetime import datetime

class RiskEngine:
    WEIGHTS = {
        "tab_switch": 15,
        "window_blur": 10,
        "clipboard_copy": 10,
        "clipboard_paste": 20,
        "new_tab": 25,
        "keyboard_copy": 10,
        "keyboard_paste": 20,
        "face_away": 15,
        "multiple_faces": 50,
        "suspicious_screen": 30,
    }

    RISK_THRESHOLDS = {
        "low": 30,
        "medium": 60,
        "high": 100
    }

    def __init__(self):
        self.events: List[Dict] = []

    def add_event(self, event_type: str, timestamp: int = None, details: str = None):
        self.events.append({
            "type": event_type,
            "timestamp": timestamp or int(datetime.utcnow().timestamp() * 1000),
            "details": details
        })

    def calculate_risk_score(self) -> int:
        score = 0
        event_counts: Dict[str, int] = {}

        for event in self.events:
            event_type = event["type"]
            event_counts[event_type] = event_counts.get(event_type, 0) + 1

        for event_type, count in event_counts.items():
            weight = self.WEIGHTS.get(event_type, 0)
            score += weight * min(count, 5)

        return min(score, 150)

    def get_risk_level(self, score: int) -> str:
        if score >= self.RISK_THRESHOLDS["high"]:
            return "high"
        elif score >= self.RISK_THRESHOLDS["medium"]:
            return "medium"
        return "low"

    def get_risk_factors(self) -> List[Dict[str, Any]]:
        factors = []
        event_counts: Dict[str, int] = {}

        for event in self.events:
            event_type = event["type"]
            event_counts[event_type] = event_counts.get(event_type, 0) + 1

        descriptions = {
            "tab_switch": "Tab switching detected",
            "window_blur": "Window focus lost",
            "clipboard_copy": "Text copied to clipboard",
            "clipboard_paste": "Text pasted from clipboard",
            "new_tab": "New tab opened",
            "keyboard_copy": "Keyboard copy shortcut used",
            "keyboard_paste": "Keyboard paste shortcut used",
            "face_away": "Face not detected in camera",
            "multiple_faces": "Multiple faces detected",
            "suspicious_screen": "Suspicious content on screen",
        }

        for event_type, count in event_counts.items():
            if count > 0:
                weight = self.WEIGHTS.get(event_type, 0)
                factors.append({
                    "event": event_type,
                    "description": descriptions.get(event_type, event_type),
                    "count": count,
                    "points_per_event": weight,
                    "total_points": weight * min(count, 5)
                })

        return sorted(factors, key=lambda x: x["total_points"], reverse=True)

    def get_risk_report(self) -> Dict[str, Any]:
        score = self.calculate_risk_score()
        level = self.get_risk_level(score)
        factors = self.get_risk_factors()

        return {
            "risk_score": score,
            "risk_level": level,
            "risk_factors": factors,
            "total_events": len(self.events),
            "recommendation": self._get_recommendation(level),
            "timestamp": int(datetime.utcnow().timestamp() * 1000)
        }

    def _get_recommendation(self, level: str) -> str:
        recommendations = {
            "low": "Candidate appears to have taken the interview honestly. Proceed with normal evaluation.",
            "medium": "Some suspicious behavior detected. Review video recordings carefully before making a decision.",
            "high": "Significant suspicious behavior detected. Manual review of video strongly recommended. Consider rejecting candidate."
        }
        return recommendations.get(level, "")

    @staticmethod
    def calculate_combined_risk(
        tab_switches: int = 0,
        clipboard_copies: int = 0,
        clipboard_pastes: int = 0,
        face_away_count: int = 0,
        multiple_faces_count: int = 0,
        suspicious_screen_count: int = 0
    ) -> Dict[str, Any]:
        engine = RiskEngine()
        
        for _ in range(min(tab_switches, 5)):
            engine.add_event("tab_switch")
        for _ in range(min(clipboard_copies, 5)):
            engine.add_event("clipboard_copy")
        for _ in range(min(clipboard_pastes, 5)):
            engine.add_event("clipboard_paste")
        for _ in range(min(face_away_count, 5)):
            engine.add_event("face_away")
        for _ in range(min(multiple_faces_count, 5)):
            engine.add_event("multiple_faces")
        for _ in range(min(suspicious_screen_count, 5)):
            engine.add_event("suspicious_screen")
        
        return engine.get_risk_report()


risk_engine = RiskEngine()
