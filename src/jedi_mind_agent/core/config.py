from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "JediMindAgent"
    app_env: str = "local"
    database_url: str
    openai_api_key: str = ""
    openai_chat_model: str = "gpt-4.1-mini"
    openai_base_url: str = "https://api.openai.com/v1"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()
