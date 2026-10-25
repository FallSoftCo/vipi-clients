from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VIPI_", env_file=None)
    database_url: str
    workos_client_id: str = Field(pattern=r"^client_[A-Za-z0-9]+$")
    workos_issuer: str
    service_secret: str = Field(min_length=43)
    environment: str = "development"
    allowed_subjects: frozenset[str] = frozenset()
    max_message_bytes: int = 65_536
    max_pending_per_recipient: int = 10_000
    delivery_seconds: int = 259_200
    bot_monthly_budget_nano_usd: int = 500_000_000

    @property
    def jwks_url(self) -> str:
        return f"https://api.workos.com/sso/jwks/{self.workos_client_id}"
