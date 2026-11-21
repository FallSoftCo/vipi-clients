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
    # Off until reviewed migration/deployment; old and shared audiences stay pinned.
    shared_identity_transition_enabled: bool = False
    service_secret: str = Field(min_length=43)
    environment: Literal["development", "test", "native-qa", "staging", "production"] = "development"
    # Startup-only hold; never inferred from an offline recovery receipt.
    recovery_hold: bool = False
    allowed_subjects: frozenset[str] = frozenset()
    # Complimentary store-review access for exact authenticated internal user IDs.
    # Separate from staging subject admission; never a purchase/receipt override.
    reviewer_user_ids: frozenset[str] = Field(default=frozenset(), max_length=32)
    # Owned testing access may precede first profile creation. Bind only to a
    # verified shared identity, never an email or a client-supplied account ID.
    reviewer_identity_subjects: frozenset[str] = Field(default=frozenset(), max_length=32)
    store_sandbox_user_ids: frozenset[str] = Field(default=frozenset(), max_length=32)
    store_sandbox_restricted: bool = False
    groups_enabled: bool = False
    max_message_bytes: int = 65_536
    max_pending_per_recipient: int = 10_000
    delivery_seconds: int = 259_200
    bot_monthly_budget_nano_usd: int = 500_000_000
    account_deletion_enabled: bool = False
    global_deletion_enabled: bool = False
    global_deletion_secret: SecretStr | None = None
    # Legacy deployment flag is accepted for compatibility; it grants no user DELETE.
    workos_dedicated_user_pool: bool = False
    workos_api_key: SecretStr | None = None
    deletion_web_origin: str | None = None
    # Accepted only so an existing deployment can upgrade without dropping its
    # environment file. Free friend messaging never consults this legacy flag.
    enforce_subscriptions: bool = False
    apple_bundle_id: str = "co.fallsoft.vipi"
    apple_app_id: int | None = None
    apple_key_id: str | None = None
    apple_issuer_id: str | None = None
    apple_private_key_path: str | None = None
    apple_root_certificate_paths: tuple[str, ...] = ()
    apple_environment: Literal["Production", "Sandbox"] = "Production"
    google_package_name: str = "co.fallsoft.vipi"
    google_service_account_path: str | None = None
    google_allow_test_purchases: bool = False
    purchase_freshness_seconds: int = Field(default=86400, ge=60, le=86400)
    purchase_outage_seconds: int = Field(default=259200, ge=300, le=259200)
    google_rtdn_audience: str | None = None
    google_rtdn_service_account: str | None = None
    google_rtdn_subscription: str | None = None
    deepseek_api_key: SecretStr | None = None
    bot_model: str = "deepseek-flash"
    bot_input_nano_usd_per_token: int = Field(default=300, ge=1)
    bot_output_nano_usd_per_token: int = Field(default=1200, ge=1)
    bot_output_tokens: int = Field(default=384, ge=64, le=512)
    bot_monthly_replies: int = Field(default=150, ge=1, le=10_000)
    bot_global_monthly_budget_nano_usd: int = Field(default=20_000_000_000, ge=1)
    fcm_project_id: str | None = None
    fcm_service_account_path: str | None = None
    apns_key_id: str | None = None
    apns_team_id: str | None = None
    apns_private_key_path: str | None = None
    apns_sandbox_key_id: str | None = None
    apns_sandbox_private_key_path: str | None = None
    apns_bundle_id: str = "co.fallsoft.vipi"
    foreground_connections_per_worker: int = Field(default=200, ge=1, le=10000)

    @model_validator(mode="after")
    def shared_identity_configuration(self):
        if self.shared_identity_transition_enabled:
            from .identity_authorities import LEGACY_VIPI, FALLSOFT_VIPI
            authority = next((a for a in (LEGACY_VIPI, FALLSOFT_VIPI) if a.client_id == self.workos_client_id), None)
            if authority is None or self.workos_issuer != authority.issuer:
                raise ValueError("Identity transition requires a reviewed pinned authority")
        return self

    @model_validator(mode="after")
    def reviewer_configuration(self):
        from uuid import UUID
        from .identity_authorities import raw_shared_subject
        for subject in self.reviewer_identity_subjects:
            raw_shared_subject(subject)
        for value in self.reviewer_user_ids | self.store_sandbox_user_ids:
            try:
                parsed = UUID(value)
            except (ValueError, AttributeError):
                raise ValueError("Reviewer and sandbox account IDs must be canonical internal UUIDs") from None
            if str(parsed) != value or parsed.int == 0:
                raise ValueError("Reviewer and sandbox account IDs must be canonical internal UUIDs")
        return self

    @model_validator(mode="after")
    def apns_sandbox_configuration(self):
        values = (self.apns_sandbox_key_id, self.apns_sandbox_private_key_path, self.apns_team_id)
        if (self.apns_sandbox_key_id or self.apns_sandbox_private_key_path) and not all(values):
            raise ValueError("APNs sandbox requires key ID, private key path and team ID")
        return self

    @model_validator(mode="after")
    def purchases_configuration(self):
        notifications = (self.google_rtdn_audience, self.google_rtdn_service_account, self.google_rtdn_subscription)
        if any(notifications) and not all(notifications):
            raise ValueError("Google notifications require audience, service account and subscription")
        if self.purchase_outage_seconds < self.purchase_freshness_seconds:
            raise ValueError("Purchase outage window must cover the reconciliation interval")
        values = (self.apple_key_id, self.apple_issuer_id, self.apple_private_key_path, self.apple_root_certificate_paths)
        if any(values) and not all(values):
            raise ValueError("Apple verification requires key, issuer and pinned root certificates")
        if all(values) and self.apple_environment == "Production" and not self.apple_app_id:
            raise ValueError("Apple production verification requires the numeric app identifier")
        if self.environment == "production" and (self.google_allow_test_purchases or self.apple_environment == "Sandbox"):
            raise ValueError("Production cannot accept store sandbox purchases")
        if self.store_sandbox_restricted and self.google_allow_test_purchases:
            raise ValueError("Restricted sandbox mode cannot accept global test purchases")
        if self.store_sandbox_restricted and all(values) and not self.apple_app_id:
            raise ValueError("Restricted Apple verification requires the numeric app identifier")
        return self

    @property
    def sandbox_restricted(self) -> bool:
        return self.environment == "production" or self.store_sandbox_restricted

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
        if self.global_deletion_enabled and (not self.global_deletion_secret or
                len(self.global_deletion_secret.get_secret_value()) < 43 or
                self.global_deletion_secret.get_secret_value() == self.service_secret):
            raise ValueError("Global deletion requires its own dedicated shared secret")
        # App-only deletion needs no provider secret and never deletes a WorkOS
        # user. The browser OAuth code exchange independently needs its secret.
        if self.deletion_web_origin:
            from urllib.parse import urlsplit
            origin = urlsplit(self.deletion_web_origin)
            if not self.workos_api_key or not self.workos_api_key.get_secret_value():
                raise ValueError("Browser deletion requires a configured sign-in credential")
            if not self.account_deletion_enabled or origin.scheme != "https" or not origin.netloc or origin.path or origin.query or origin.fragment or origin.username or origin.password:
                raise ValueError("Browser deletion requires an enabled service and a fixed HTTPS origin")
        return self

    @property
    def jwks_url(self) -> str:
        return f"https://api.workos.com/sso/jwks/{self.workos_client_id}"
