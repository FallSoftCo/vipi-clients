"""Request bodies for the core HTTP API."""
import unicodedata
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, SecretStr, StrictBool, field_validator


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProfileInput(Input):
    username: str = Field(min_length=3, max_length=24)
    display_name: str = Field(min_length=1, max_length=80)

    @field_validator("display_name")
    @classmethod
    def clean_name(cls, value):
        value = value.strip()
        if not value or any(unicodedata.category(c).startswith("C") for c in value):
            raise ValueError("invalid_name")
        return value


class DeleteAccountInput(Input):
    account_id: UUID
    receipt_secret: str = Field(pattern=r"^[A-Za-z0-9_-]{43}$")


class IdentityLinkInput(Input):
    request_id: UUID
    expected_account_id: UUID
    fallsoft_access_token: SecretStr = Field(min_length=1, max_length=16_384, repr=False)


class DeviceInput(Input):
    device_id: UUID
    secret: str = Field(min_length=43, max_length=43, repr=False)
    replace_active: bool = False


class ChatFeaturesInput(Input):
    version: int = Field(strict=True, ge=0, le=1)


class SendInput(Input):
    required_chat_features_version: int = Field(default=0, strict=True, ge=0, le=1)
    id: UUID
    recipient_id: UUID
    recipient_device_id: UUID
    created_at: AwareDatetime
    cipher_type: Literal[2, 3]
    ciphertext: str = Field(min_length=44, max_length=87_384, repr=False)
    attachment_ids: list[UUID] = Field(default_factory=list, max_length=8)


class TypingInput(Input):
    active: StrictBool


class SurveyInput(Input):
    choice: Literal["yes", "maybe", "no", "skip"]


class ReceiptsInput(Input):
    seen: list[UUID] = Field(default_factory=list, max_length=64)
    check: list[UUID] = Field(default_factory=list, max_length=64)


class BlockInput(Input):
    blocked: bool


class ClaimInput(Input):
    request_id: UUID


class ApplePurchaseInput(Input):
    signed_transaction_info: str = Field(min_length=20, max_length=30_000, repr=False)


class GooglePurchaseInput(Input):
    purchase_token: str = Field(min_length=1, max_length=4096, repr=False)


class BotMessageInput(Input):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8192, repr=False)


class BotInput(Input):
    request_id: UUID
    consent_version: str = Field(max_length=32)
    messages: list[BotMessageInput] = Field(min_length=1, max_length=12)


class NotificationEnvelopeInput(Input):
    ticket: str = Field(min_length=80, max_length=1024)


class PushInput(Input):
    provider: Literal["fcm", "apns"]
    environment: Literal["production", "sandbox"]
    token: str = Field(min_length=20, max_length=4096, repr=False)


class BotReportInput(Input):
    request_id: UUID
    reason: Literal["harmful", "inaccurate", "other"]
    selected_reply: str = Field(min_length=1, max_length=4000, repr=False)


class LocalBotReportInput(Input):
    report_id: UUID
    provider: Literal["gemini-nano", "apple-foundation-models"]
    reason: Literal["harmful", "inaccurate", "other"]
    selected_reply: str = Field(min_length=1, max_length=4000, repr=False)
    consent_version: str = Field(max_length=32)


class UserReportInput(Input):
    report_id: UUID
    reported_user_id: UUID
    message_id: UUID | None = None
    reason: Literal["spam", "harassment", "harmful", "other"]
    selected_text: str | None = Field(default=None, max_length=32768, repr=False)
    consent_version: str = Field(max_length=32)
