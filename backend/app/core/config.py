from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    PROJECT_NAME: str = "AI Interviewer"
    VERSION: str = "1.0.0"
    API_PREFIX: str = "/api/v1"
    
    DATABASE_URL: str = "sqlite:///./ai_interviewer.db"
    
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    GEMINI_API_KEY: str = ""
    
    # LiveKit Configuration (free tier at livekit.io)
    LIVEKIT_URL: str = "wss://your-project.livekit.cloud"
    LIVEKIT_API_KEY: str = ""
    LIVEKIT_API_SECRET: str = ""
    
    class Config:
        env_file = ".env"

settings = Settings()
