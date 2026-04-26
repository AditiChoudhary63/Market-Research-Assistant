import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    LLM_MODEL: str = "gpt-4o"
    OPENAI_API_KEY: str
    PINECONE_API_KEY: str
    TAVILY_API_KEY: str
    MONGODB_URI: str
    
    # Optional settings with defaults
    JWT_SECRET: str = "super-secret-dev-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 1 week
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin123"
    USER_AGENT: str = "MarketIntelligenceBot/1.0"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()

# Inject API keys into os.environ for LangChain wrappers
os.environ["OPENAI_API_KEY"] = settings.OPENAI_API_KEY
os.environ["PINECONE_API_KEY"] = settings.PINECONE_API_KEY
os.environ["TAVILY_API_KEY"] = settings.TAVILY_API_KEY
os.environ["USER_AGENT"] = settings.USER_AGENT
