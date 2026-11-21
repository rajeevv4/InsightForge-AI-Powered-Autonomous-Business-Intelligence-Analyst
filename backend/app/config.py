import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")


class Settings:
    PROJECT_NAME: str = "InsightForge — AI-Powered Autonomous BI Analyst"
    VERSION: str = "0.1.0"
    API_PREFIX: str = "/api"

    DB_HOST: str = os.getenv("DB_HOST", "localhost")
    DB_PORT: str = os.getenv("DB_PORT", "5432")
    DB_NAME: str = os.getenv("DB_NAME", "insightforge")
    DB_USER: str = os.getenv("DB_USER", "postgres")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "")
    DB_SCHEMA: str = os.getenv("DB_SCHEMA", "insightforge")

    # Read-Only Database Role (SELECT-only on insightforge schema)
    DB_RO_USER: str = os.getenv("DB_RO_USER", "insightforge_ro")
    DB_RO_PASSWORD: str = os.getenv("DB_RO_PASSWORD", "insightforge_ro_pass")

    CORS_ORIGINS: list = ["http://localhost:3000", "http://localhost:5173", "http://127.0.0.1:3000"]

    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    # Rate Limiting
    RATE_LIMIT_AI_ASK: str = os.getenv("RATE_LIMIT_AI_ASK", "30/minute")
    RATE_LIMIT_VOICE_TRANSCRIBE: str = os.getenv("RATE_LIMIT_VOICE_TRANSCRIBE", "10/minute")


settings = Settings()
