"""Source-only Settings contracts: inert URLs are parsed, never connected.
No production credentials or provider/session/rotation policy is supplied here.
"""
import pytest

from vipi.config import Settings


def configuration(**changes):
    return Settings(**(dict(database_url="sqlite+aiosqlite://", workos_client_id="client_fixture",
        workos_issuer="https://api.workos.com", service_secret="s" * 43) | changes))


@pytest.mark.parametrize("environment", ["stagng", "prod", "STAGING", "nativeqa"],
    ids=["misspelling", "undocumented-alias", "uppercase", "wrong-qa-label"])
def test_s2_unknown_environment_is_rejected_without_input_echo(environment):
    with pytest.raises(ValueError) as error:
        configuration(environment=environment)
    assert "input_value=" not in str(error.value)


@pytest.mark.parametrize("environment", ["staging", "production"])
@pytest.mark.parametrize("url", ["sqlite+aiosqlite:///s2-synthetic-never-live",
    "mysql+pymysql://fixture:s2-synthetic-never-live@fixture.invalid/test",
    "not-a-url-s2-synthetic-never-live"], ids=["sqlite", "non-postgresql", "malformed"])
def test_s2_deployed_database_rejects_non_postgresql_without_url_echo(environment, url):
    with pytest.raises(ValueError) as error:
        configuration(environment=environment, database_url=url)
    assert url not in str(error.value)
    assert "s2-synthetic-never-live" not in str(error.value)
    assert "input_value=" not in str(error.value)


@pytest.mark.parametrize("environment", ["development", "test", "native-qa"])
def test_s2_explicit_local_modes_retain_sqlite(environment):
    settings = configuration(environment=environment)
    assert settings.environment == environment
    assert settings.database_url == "sqlite+aiosqlite://"


@pytest.mark.parametrize("environment", ["staging", "production"])
@pytest.mark.parametrize("url", ["postgresql+asyncpg://fixture.invalid/test?ssl=require",
    "postgresql://fixture.invalid/test"], ids=["asyncpg-unaltered", "postgresql-unaltered"])
def test_s2_postgresql_url_and_driver_are_not_rewritten(environment, url):
    settings = configuration(environment=environment, database_url=url, enforce_subscriptions=True)
    assert settings.environment == environment
    assert settings.database_url == url


def test_free_production_requires_no_billing_provider_or_entitlement_flag():
    value = configuration(environment="production", database_url="postgresql+asyncpg://fixture.invalid/test")
    assert not value.enforce_subscriptions


@pytest.mark.parametrize("store_settings", [
    {"google_allow_test_purchases": True},
    {"apple_environment": "Sandbox"},
], ids=["google-test-purchases", "apple-sandbox"])
def test_production_rejects_store_test_environments(store_settings):
    with pytest.raises(ValueError, match="Production cannot accept store sandbox purchases"):
        configuration(environment="production", database_url="postgresql+asyncpg://fixture.invalid/test",
            enforce_subscriptions=True, **store_settings)


@pytest.mark.parametrize("environment", ["test", "native-qa", "staging"])
def test_nonproduction_can_explicitly_accept_store_test_purchases(environment):
    url = "postgresql+asyncpg://fixture.invalid/test" if environment == "staging" else "sqlite+aiosqlite://"
    settings = configuration(environment=environment, database_url=url, google_allow_test_purchases=True,
        apple_environment="Sandbox")
    assert settings.google_allow_test_purchases and settings.apple_environment == "Sandbox"


def test_store_sandbox_allowlist_requires_canonical_uuid_and_is_separate_from_reviewers():
    from uuid import uuid4
    account = str(uuid4())
    configured = configuration(environment='production', database_url='postgresql+asyncpg://fixture.invalid/test',
        enforce_subscriptions=True, store_sandbox_user_ids=frozenset({account}))
    assert configured.store_sandbox_user_ids == {account} and not configured.reviewer_user_ids
    with pytest.raises(ValueError):
        configuration(store_sandbox_user_ids=frozenset({'not-a-uuid'}))


def test_restricted_staging_rejects_global_test_acceptance():
    with pytest.raises(ValueError, match='Restricted sandbox mode cannot accept global test purchases'):
        configuration(environment='staging', database_url='postgresql+asyncpg://fixture.invalid/test',
            store_sandbox_restricted=True, google_allow_test_purchases=True)
