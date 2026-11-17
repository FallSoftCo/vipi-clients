"""Reviewed identity authorities; unverified claims never choose an endpoint."""
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class IdentityAuthority:
    id: str
    client_id: str
    issuer: str
    jwks_url: str


LEGACY_VIPI = IdentityAuthority(
    "vipi-production", "client_01M6VYVQQ9GWVNS95DFGABXEW9",
    "https://api.workos.com/user_management/client_01M6VYVQQ9GWVNS95DFGABXEW9",
    "https://api.workos.com/sso/jwks/client_01M6VYVQQ9GWVNS95DFGABXEW9")
FALLSOFT_VIPI = IdentityAuthority(
    "fallsoft-vipi-production", "client_01M7N9Y2DGSJJVT1ZV6TY7DTZ4",
    "https://api.workos.com/user_management/client_01JPK69ZZFHH0NSP8BY2HGRDX6",
    "https://api.workos.com/sso/jwks/client_01JPK69ZZFHH0NSP8BY2HGRDX6")


def canonical_shared_subject(raw_subject: str) -> str:
    """Central Fallsoft adapters call this once before Vipi lookup/ledger erase.

    Input is the already verified raw shared WorkOS user ID, never an email.
    Other applications' client audiences are not accepted by this helper/API.
    """
    if not re.fullmatch(r"user_[A-Za-z0-9_]{1,123}", raw_subject):
        raise ValueError("invalid_shared_subject")
    return FALLSOFT_VIPI.id + ":" + raw_subject


def raw_shared_subject(canonical: str) -> str:
    prefix = FALLSOFT_VIPI.id + ":"
    if not canonical.startswith(prefix):
        raise ValueError("wrong_identity_authority")
    raw = canonical[len(prefix):]
    if canonical_shared_subject(raw) != canonical:
        raise ValueError("invalid_shared_subject")
    return raw
