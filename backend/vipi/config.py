from typing import Literal
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError
from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VIPI_", env_file=None, hide_input_in_errors=True)
    database_url: str
    workos_client_id: str = Field(pattern=r"^client_[A-Za-z0-9]+$")
    workos_issuer: str
    service_secret: str = Field(min_length=43)
    environment: Literal["development", "test", "native-qa", "staging", "production"] = "development"
    allowed_subjects: frozenset[str] = frozenset()
    max_message_bytes: int = 65_536
    max_pending_per_recipient: int = 10_000
    delivery_seconds: int = 259_200
    bot_monthly_budget_nano_usd: int = 500_000_000
    account_deletion_enabled: bool = False
    workos_dedicated_user_pool: bool = False
    workos_api_key: SecretStr | None = None
    deletion_web_origin: str | None = None

    @model_validator(mode="after")
    def deployment_database(self):
        if self.environment in {"staging", "production"}:
            try:
                backend = make_url(self.database_url).get_backend_name()
            except (ArgumentError, ValueError):
                raise ValueError("Staging and production require a PostgreSQL database URL") from None
            if backend != "postgresql":
                raise ValueError("Staging and production require a PostgreSQL database URL")
        return self

    @model_validator(mode="after")
    def deletion_configuration(self):
        # WorkOS users can be shared by applications in an environment. Never
        # delete that shared identity without a verified Vipi-only user pool.
        if self.account_deletion_enabled and (not self.workos_dedicated_user_pool or not self.workos_api_key or not self.workos_api_key.get_secret_value()):
            raise ValueError("Account deletion requires a configured, dedicated Vipi identity pool")
        if self.deletion_web_origin:
            from urllib.parse import urlsplit
            origin = urlsplit(self.deletion_web_origin)
            if not self.account_deletion_enabled or origin.scheme != "https" or not origin.netloc or origin.path or origin.query or origin.fragment or origin.username or origin.password:
                raise ValueError("Browser deletion requires an enabled service and a fixed HTTPS origin")
        return self

    @property
    def jwks_url(self) -> str:
        return f"https://api.workos.com/sso/jwks/{self.workos_client_id}"
