from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import List, Optional, Union


PLACEHOLDER_SECRET = "your-secret-key-change-in-production"


class Settings(BaseSettings):
    PROJECT_NAME: str = "AI Interviewer"
    VERSION: str = "1.0.0"
    API_PREFIX: str = "/api/v1"

    DATABASE_URL: str = "sqlite:///./ai_interviewer.db"

    # SECRET_KEY MUST be provided via env. No safe default.
    SECRET_KEY: str = ""
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    GEMINI_API_KEY: str = ""

    # CORS — comma-separated list of allowed origins.
    # Use a value other than "*" in production; "*" is forbidden together with
    # credentials and our middleware sets allow_credentials=True.
    CORS_ORIGINS: Union[str, List[str]] = "http://localhost:3000,http://127.0.0.1:3000"

    # Upload limits
    MAX_UPLOAD_SIZE: int = 50 * 1024 * 1024  # 50 MB

    # Phase 2.4: content-side follow-up question. When enabled, the
    # background-transcription task auto-evaluates the answer and, if
    # `rubric_score >= FOLLOWUP_THRESHOLD`, asks Gemini to generate one
    # follow-up that anchors to a specific claim in the candidate's
    # actual answer. The follow-up is persisted as a new Question row
    # (source="followup") and the frontend polls for it after submit.
    # Off by default until tested in production with real candidates.
    # Cost: one extra Gemini call per strong answer; bounded by the cap.
    ENABLE_FOLLOWUP_QUESTIONS: bool = False
    FOLLOWUP_THRESHOLD: float = 3.0
    MAX_FOLLOWUPS_PER_INTERVIEW: int = 3

    @field_validator("SECRET_KEY")
    @classmethod
    def _validate_secret_key(cls, v: str) -> str:
        if not v or v == PLACEHOLDER_SECRET:
            raise ValueError(
                "SECRET_KEY must be set to a strong random value via the "
                "environment (e.g. backend/.env). The placeholder default is "
                "rejected. Generate one with: python -c \"import secrets; "
                "print(secrets.token_urlsafe(64))\""
            )
        if len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters long.")
        return v

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _split_cors(cls, v):
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    def cors_origin_list(self) -> List[str]:
        if isinstance(self.CORS_ORIGINS, list):
            return self.CORS_ORIGINS
        return [o.strip() for o in str(self.CORS_ORIGINS).split(",") if o.strip()]

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
