import os


class Config:
    APP_NAME = os.getenv("APP_NAME", "hireinsight")
    ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///hireinsight_demo.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JWT_SECRET = os.getenv("JWT_SECRET", "demo-secret")
    JWT_EXPIRY_HOURS = int(os.getenv("JWT_EXPIRY_HOURS", "8"))
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")
    SEED_DEMO_DATA = os.getenv("SEED_DEMO_DATA", "true").lower() == "true"
    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "uploads")
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", str(16 * 1024 * 1024)))
    LLM_ENABLED = os.getenv("LLM_ENABLED", "true").lower() == "true"
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "deepseek")
    LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")
    LLM_API_URL = os.getenv("LLM_API_URL", "https://api.deepseek.com/v1/chat/completions")
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY") or os.getenv("API_KEY") or os.getenv("LLM_API_KEY")
    SECURITY_HEADERS_ENABLED = os.getenv("SECURITY_HEADERS_ENABLED", "true").lower() == "true"
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
    RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "120"))
    TRUST_PROXY_COUNT = int(os.getenv("TRUST_PROXY_COUNT", "1"))
    MAX_UPLOAD_FILES = int(os.getenv("MAX_UPLOAD_FILES", "20"))
    MAX_ARCHIVE_FILES = int(os.getenv("MAX_ARCHIVE_FILES", "50"))
    MAX_ARCHIVE_UNCOMPRESSED_SIZE = int(os.getenv("MAX_ARCHIVE_UNCOMPRESSED_SIZE", str(64 * 1024 * 1024)))
    MAX_ARCHIVE_COMPRESSION_RATIO = int(os.getenv("MAX_ARCHIVE_COMPRESSION_RATIO", "100"))


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    JWT_SECRET = "test-secret"
    SEED_DEMO_DATA = True
    UPLOAD_FOLDER = "test_uploads"
    LLM_ENABLED = False
    RATE_LIMIT_ENABLED = False
