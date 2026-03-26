from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore",
    )

    APP_NAME: str = "Sports Platform"
    DEBUG: bool = False

    DATABASE_URL: str

    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # Origens permitidas pelo CORS, separadas por vírgula.
    # Exemplo: https://sports.netlify.app,http://localhost:3000
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:5500"

    # Brevo (Sendinblue) — envio de email transacional
    BREVO_API_KEY: str = ""
    EMAIL_FROM: str = "noreply@jogossinodal.com.br"
    EMAIL_FROM_NAME: str = "Jogos Sinodais"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]


settings = Settings()
