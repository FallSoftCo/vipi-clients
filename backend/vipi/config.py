from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VIPI_", env_file=None, hide_input_in_errors=True)
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
    account_deletion_enabled: bool = False
    workos_dedicated_user_pool: bool = False
    workos_api_key: SecretStr | None = None

    @model_validator(mode="after")
    def deletion_configuration(self):
        # WorkOS users can be shared by applications in an environment. Never
        # delete that shared identity without a verified Vipi-only user pool.
        if self.account_deletion_enabled and (not self.workos_dedicated_user_pool or not self.workos_api_key or not self.workos_api_key.get_secret_value()):
            raise ValueError("Account deletion requires a configured, dedicated Vipi identity pool")
        return self

    @property
    def jwks_url(self) -> str:
        return f"https://api.workos.com/sso/jwks/{self.workos_client_id}"
