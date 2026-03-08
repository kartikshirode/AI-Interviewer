import os
import asyncio
from typing import Optional
from app.core.config import settings

class LiveKitService:
    def __init__(self):
        self.url = settings.LIVEKIT_URL
        self.api_key = settings.LIVEKIT_API_KEY
        self.api_secret = settings.LIVEKIT_API_SECRET
        
    def generate_token(
        self,
        room_name: str,
        participant_name: str,
        is_agent: bool = False
    ) -> str:
        """Generate access token for a participant"""
        if not self.api_key or not self.api_secret or self.api_key == "your-api-key":
            raise ValueError("LiveKit credentials not configured")
        
        # Use PyJWT directly to generate token
        import jwt
        from datetime import datetime, timedelta
        
        now = datetime.utcnow()
        exp = now + timedelta(hours=1)
        
        payload = {
            "iss": self.api_key,
            "sub": participant_name,
            "aud": self.url,
            "nbf": int(now.timestamp()),
            "exp": int(exp.timestamp()),
            "jti": f"{room_name}_{participant_name}",
        }
        
        if is_agent:
            payload["can_publish"] = False
            payload["can_subscribe"] = True
        else:
            payload["can_publish"] = True
            payload["can_subscribe"] = True
            
        token = jwt.encode(payload, self.api_secret, algorithm="HS256")
        return token

livekit_service = LiveKitService()
