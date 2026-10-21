from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    supabase_url: str
    supabase_service_role_key: str
    supabase_anon_key: str | None = None
    frontend_origin: str = "http://localhost:5173"
    appointed_only: bool = False
    cookie_secure: bool = False
    cookie_samesite: str | None = None

    # Google Drive Integration settings
    google_service_account_file: str | None = None
    google_service_account_json: str | None = None
    google_drive_folder_id: str | None = None
    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_refresh_token: str | None = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def allowed_origins(self) -> list[str]:
        """Parse comma-separated origins, stripping whitespace and trailing slashes."""
        raw_origins = self.frontend_origin.split(",")
        cleaned = [o.strip().rstrip("/") for o in raw_origins if o.strip()]
        return cleaned or ["http://localhost:5173"]


settings = Settings()
