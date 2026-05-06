"""应用配置模块，负责从环境变量读取设置。"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """GIIM 应用配置。"""

    app_env: str = Field(default="dev", alias="APP_ENV", description="应用运行环境")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL", description="日志级别")
    database_url: str = Field(alias="DATABASE_URL", description="PostgreSQL 异步连接地址")
    qdrant_url: str = Field(alias="QDRANT_URL", description="Qdrant 服务地址")
    qdrant_api_key: str = Field(default="", alias="QDRANT_API_KEY", description="Qdrant API Key")
    deepseek_api_key: str = Field(default="", alias="DEEPSEEK_API_KEY", description="DeepSeek API Key")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY", description="OpenAI API Key")
    anthropic_api_key: str = Field(
        default="", alias="ANTHROPIC_API_KEY", description="Anthropic API Key"
    )
    embedding_api_key: str = Field(
        default="", alias="EMBEDDING_API_KEY", description="Embedding API Key"
    )

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
