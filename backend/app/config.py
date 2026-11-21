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
    RATE_LIMIT_DATASET_UPLOAD: str = os.getenv("RATE_LIMIT_DATASET_UPLOAD", "5/hour")

    # Dataset Workspace Limits (Level 5)
    MAX_FILE_SIZE_MB: int = int(os.getenv("MAX_FILE_SIZE_MB", "25"))
    MAX_ROWS_PER_TABLE: int = int(os.getenv("MAX_ROWS_PER_TABLE", "200000"))
    MAX_COLUMNS_PER_TABLE: int = int(os.getenv("MAX_COLUMNS_PER_TABLE", "100"))
    MAX_DATASETS_PER_OWNER: int = int(os.getenv("MAX_DATASETS_PER_OWNER", "3"))
    DATASET_EXPIRY_HOURS: int = int(os.getenv("DATASET_EXPIRY_HOURS", "24"))
    MAX_TOTAL_DB_MB: int = int(os.getenv("MAX_TOTAL_DB_MB", "450"))
    # XLSX-specific safety limits
    XLSX_MAX_SHEETS: int = int(os.getenv("XLSX_MAX_SHEETS", "20"))
    XLSX_MAX_UNCOMPRESSED_MB: int = int(os.getenv("XLSX_MAX_UNCOMPRESSED_MB", "500"))

    # Proxy and abuse controls
    TRUSTED_PROXIES_ENABLED: bool = os.getenv("TRUSTED_PROXIES_ENABLED", "false").lower() in ("true", "1", "yes")
    MAX_DATASETS_PER_IP_PER_DAY: int = int(os.getenv("MAX_DATASETS_PER_IP_PER_DAY", "20"))
    MAX_GLOBAL_DATASETS: int = int(os.getenv("MAX_GLOBAL_DATASETS", "100"))


settings = Settings()
