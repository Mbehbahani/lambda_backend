"""
Application configuration via environment variables.
Uses pydantic-settings for validation and type safety.
"""

from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── App ──────────────────────────────────────────────
    app_name: str = "LLMBackend"
    app_version: str = "0.1.0"
    debug: bool = False
    log_level: str = "INFO"

    # ── AWS / Bedrock ────────────────────────────────────
    # Note: AWS_REGION is automatically provided by Lambda environment
    # For local dev, you can set it or use boto3's automatic detection
    aws_region: str = "us-east-1"  # Default, will be overridden by Lambda's AWS_REGION
    bedrock_model_id: str = "us.anthropic.claude-3-5-haiku-20241022-v1:0"
    bedrock_max_tokens: int = 1024
    bedrock_temperature: float = 0.7

    # ── Supabase ─────────────────────────────────────────
    supabase_url: str = ""
    supabase_service_role_key: str = ""

    # ── CORS ─────────────────────────────────────────────
    cors_origins: str = "http://localhost:3000"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
