from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Personal Task Tracker"
    public_base_url: str = ""
    database_url: str = "sqlite:///./task_tracker.db"
    task_tracker_api_key: str = "change-me"
    session_secret_key: str = "change-this-long-random-string"
    session_cookie_https: bool = False
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    allowed_google_emails: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def google_oauth_enabled(self) -> bool:
        return bool(self.google_oauth_client_id and self.google_oauth_client_secret)

    @property
    def normalized_public_base_url(self) -> str:
        return self.public_base_url.rstrip("/")

    @property
    def allowed_email_set(self) -> set[str]:
        return {
            email.strip().lower()
            for email in self.allowed_google_emails.split(",")
            if email.strip()
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
