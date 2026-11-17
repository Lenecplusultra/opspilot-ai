from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    environment: str = "development"
    database_url: str = "sqlite:///./opspilot.db"

    secret_key: str = "dev-only-secret-change-me-32-bytes-min!"
    access_token_expire_minutes: int = 60
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # Agent
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    agent_max_steps: int = 8

    # Connectors
    runbook_dir: Path = BACKEND_DIR / "runbooks"
    github_repo: str = ""  # "owner/repo" switches the GitHub connector to the live API
    github_token: str = ""

    # Demo
    demo_scenario: str = "payments_stuck_worker"
    seed_password: str = "password"


settings = Settings()
