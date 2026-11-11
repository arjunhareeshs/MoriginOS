import pytest

from marginos.core.config import Settings


def test_production_refuses_skip_verify(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("PAYPAL_WEBHOOK_SKIP_VERIFY", "true")
    with pytest.raises(ValueError):
        Settings(_env_file=None)


def test_development_allows_skip_verify(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("PAYPAL_WEBHOOK_SKIP_VERIFY", "true")
    assert Settings(_env_file=None).paypal_webhook_skip_verify is True


def test_settings_never_repr_secret(monkeypatch):
    monkeypatch.setenv("PAYPAL_CLIENT_SECRET", "abc-secret-value")
    settings = Settings(_env_file=None)
    assert "abc-secret-value" not in repr(settings)
    assert "abc-secret-value" not in str(settings)
    assert settings.paypal_client_secret.get_secret_value() == "abc-secret-value"
