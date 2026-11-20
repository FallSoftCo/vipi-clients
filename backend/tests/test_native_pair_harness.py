"""The explicit native harness cannot inherit a production environment."""
import importlib.util
from pathlib import Path


def harness():
    spec = importlib.util.spec_from_file_location("native_pair", Path(__file__).resolve().parents[2] / "scripts/serve-isolated-native-pair.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_isolated_settings_ignore_live_environment_and_keep_real_authority(tmp_path, monkeypatch):
    monkeypatch.setenv("VIPI_DATABASE_URL", "postgresql+asyncpg://live.invalid/production")
    monkeypatch.setenv("VIPI_WORKOS_API_KEY", "synthetic-live-admin-never-use")
    monkeypatch.setenv("VIPI_DEEPSEEK_API_KEY", "synthetic-paid-provider-never-use")
    monkeypatch.setenv("VIPI_FCM_SERVICE_ACCOUNT_PATH", "/live/provider/secret")
    monkeypatch.setenv("VIPI_RECOVERY_HOLD", "true")
    module = harness()
    subjects = ["fallsoft-vipi-production:user_pair_a", "fallsoft-vipi-production:user_pair_b"]
    settings = module.settings_for(tmp_path, subjects)
    assert settings.database_url == f"sqlite+aiosqlite:///{tmp_path / 'pair.sqlite'}"
    assert settings.allowed_subjects == frozenset(subjects)
    assert settings.shared_identity_transition_enabled
    assert settings.workos_client_id == module.FALLSOFT_VIPI.client_id
    assert settings.workos_api_key is None and settings.deepseek_api_key is None
    assert settings.fcm_service_account_path is None and settings.apple_private_key_path is None
    assert settings.apns_private_key_path is None and settings.google_service_account_path is None
    assert not settings.recovery_hold
    assert not settings.account_deletion_enabled and not settings.global_deletion_enabled
