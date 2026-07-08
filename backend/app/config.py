import os


class Config:
    APP_NAME = os.getenv("APP_NAME", "hireinsight")
    ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///hireinsight_demo.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    AUTO_CREATE_DB = os.getenv("AUTO_CREATE_DB", "false" if ENVIRONMENT == "production" else "true").lower() == "true"
    JWT_SECRET = os.getenv("JWT_SECRET", "demo-secret")
    JWT_EXPIRY_HOURS = int(os.getenv("JWT_EXPIRY_HOURS", "8"))
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")
    SEED_DEMO_DATA = os.getenv("SEED_DEMO_DATA", "true").lower() == "true"
    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "uploads")
    BACKUP_FOLDER = os.getenv("BACKUP_FOLDER", "backups")
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", str(16 * 1024 * 1024)))
    LLM_ENABLED = os.getenv("LLM_ENABLED", "true").lower() == "true"
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "deepseek")
    LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")
    LLM_API_URL = os.getenv("LLM_API_URL", "https://api.deepseek.com/v1/chat/completions")
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY") or os.getenv("API_KEY") or os.getenv("LLM_API_KEY")
    LLM_TIMEOUT_SECONDS = int(os.getenv("LLM_TIMEOUT_SECONDS", "45"))
    LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "1"))
    LLM_RETRY_BACKOFF_SECONDS = float(os.getenv("LLM_RETRY_BACKOFF_SECONDS", "0.5"))
    LLM_USAGE_LOG_ENABLED = os.getenv("LLM_USAGE_LOG_ENABLED", "true").lower() == "true"
    LLM_PROMPT_PRICE_PER_1M_TOKENS_USD = float(os.getenv("LLM_PROMPT_PRICE_PER_1M_TOKENS_USD", "0"))
    LLM_COMPLETION_PRICE_PER_1M_TOKENS_USD = float(os.getenv("LLM_COMPLETION_PRICE_PER_1M_TOKENS_USD", "0"))
    LLM_DAILY_CALL_LIMIT = int(os.getenv("LLM_DAILY_CALL_LIMIT", "0"))
    LLM_DAILY_COST_LIMIT_USD = float(os.getenv("LLM_DAILY_COST_LIMIT_USD", "0"))
    LLM_FAILURE_RATE_WARN_PERCENT = float(os.getenv("LLM_FAILURE_RATE_WARN_PERCENT", "20"))
    SECURITY_HEADERS_ENABLED = os.getenv("SECURITY_HEADERS_ENABLED", "true").lower() == "true"
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    ACCESS_LOG_ENABLED = os.getenv("ACCESS_LOG_ENABLED", "true").lower() == "true"
    SLOW_REQUEST_MS = int(os.getenv("SLOW_REQUEST_MS", "1000"))
    RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
    RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "120"))
    LOGIN_MAX_FAILURES = int(os.getenv("LOGIN_MAX_FAILURES", "5"))
    LOGIN_LOCKOUT_MINUTES = int(os.getenv("LOGIN_LOCKOUT_MINUTES", "15"))
    INTERVIEW_ROOM_TOKEN_HOURS = int(os.getenv("INTERVIEW_ROOM_TOKEN_HOURS", "72"))
    PUBLIC_INTERVIEW_MAX_REQUESTS_PER_MINUTE = int(os.getenv("PUBLIC_INTERVIEW_MAX_REQUESTS_PER_MINUTE", "60"))
    PUBLIC_INTERVIEW_MAX_ANSWER_CHARS = int(os.getenv("PUBLIC_INTERVIEW_MAX_ANSWER_CHARS", "4000"))
    PUBLIC_INTERVIEW_MAX_MESSAGES = int(os.getenv("PUBLIC_INTERVIEW_MAX_MESSAGES", "80"))
    PUBLIC_INTERVIEW_MAX_CHEAT_EVENTS = int(os.getenv("PUBLIC_INTERVIEW_MAX_CHEAT_EVENTS", "100"))
    SPEECH_PROVIDER = os.getenv("SPEECH_PROVIDER", "browser")
    SPEECH_ASR_ENABLED = os.getenv("SPEECH_ASR_ENABLED", "true").lower() == "true"
    SPEECH_TTS_ENABLED = os.getenv("SPEECH_TTS_ENABLED", "true").lower() == "true"
    SPEECH_ASR_API_URL = os.getenv("SPEECH_ASR_API_URL", "")
    SPEECH_TTS_API_URL = os.getenv("SPEECH_TTS_API_URL", "")
    SPEECH_API_KEY = os.getenv("SPEECH_API_KEY", "")
    SPEECH_MAX_AUDIO_BYTES = int(os.getenv("SPEECH_MAX_AUDIO_BYTES", str(8 * 1024 * 1024)))
    SPEECH_TTS_MAX_CHARS = int(os.getenv("SPEECH_TTS_MAX_CHARS", "1000"))
    TRUST_PROXY_COUNT = int(os.getenv("TRUST_PROXY_COUNT", "1"))
    AUDIT_LOG_RETENTION_DAYS = int(os.getenv("AUDIT_LOG_RETENTION_DAYS", "365"))
    LLM_USAGE_RETENTION_DAYS = int(os.getenv("LLM_USAGE_RETENTION_DAYS", "180"))
    TASK_RETENTION_DAYS = int(os.getenv("TASK_RETENTION_DAYS", "90"))
    MAX_UPLOAD_FILES = int(os.getenv("MAX_UPLOAD_FILES", "20"))
    MAX_ARCHIVE_FILES = int(os.getenv("MAX_ARCHIVE_FILES", "50"))
    MAX_ARCHIVE_UNCOMPRESSED_SIZE = int(os.getenv("MAX_ARCHIVE_UNCOMPRESSED_SIZE", str(64 * 1024 * 1024)))
    MAX_ARCHIVE_COMPRESSION_RATIO = int(os.getenv("MAX_ARCHIVE_COMPRESSION_RATIO", "100"))


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    JWT_SECRET = "test-secret"
    SEED_DEMO_DATA = True
    AUTO_CREATE_DB = True
    UPLOAD_FOLDER = "test_uploads"
    LLM_ENABLED = False
    RATE_LIMIT_ENABLED = False
