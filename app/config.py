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
    # Only this email may create a NEW account via Google login -- this app
    # has no concept of multiple users, so leaving sign-up open lets any
    # Google account self-register. None keeps the old (open) behavior, so
    # a missing/misconfigured env var can never lock the real user out.
    allowed_email: str | None = None
    # The app always runs with `--proxy-headers` behind a reverse proxy, and
    # Google OAuth itself requires an HTTPS redirect URI for any non-
    # localhost origin -- so the real deployment is HTTPS-only already, and
    # the session cookie should carry the Secure flag. Kept overridable
    # (rather than hardcoded) in case that assumption is ever wrong for a
    # given environment (e.g. plain-HTTP LAN access), so fixing it never
    # requires a code change.
    session_cookie_secure: bool = True


settings = Settings()
