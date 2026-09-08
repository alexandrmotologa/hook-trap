from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application runtime configuration."""

    model_config = SettingsConfigDict(
        env_prefix="HOOK_TRAP_",
        env_file=".env",
        extra="ignore",
    )

    host: str = "127.0.0.1"
    port: int = 8080
    db_path: str = "hook_trap.db"
    default_auto_forward_url: str | None = None
    cors_origins: list[str] = ["*"]
    replay_timeout: float = 10.0
    public_tunnel_url: str | None = None


settings = Settings()
