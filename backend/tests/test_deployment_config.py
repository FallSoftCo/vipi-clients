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


def test_production_cannot_disable_verified_subscriptions():
    with pytest.raises(ValueError, match="Production requires verified subscriptions"):
        configuration(environment="production", database_url="postgresql+asyncpg://fixture.invalid/test")
