from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    google_client_id: str
    google_client_secret: str
    session_secret_key: str
    vapid_public_key: str
    vapid_private_key: str
    vapid_subject: str


settings = Settings()
