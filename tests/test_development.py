"""Development onboarding creates a usable administrator without leaking secrets."""

import json
import subprocess
from unittest.mock import patch

import pytest

from homeassistant import auth
from homeassistant.auth.providers.homeassistant import InvalidAuth
from homeassistant.components.onboarding import (
    STORAGE_KEY,
    STORAGE_VERSION,
    OnboardingStorage,
)
from homeassistant.components.onboarding.const import STEPS
from scripts.dev import DevelopmentError, bootstrap_admin, prepare, read_credentials
from scripts.ha_bootstrap import initialize_admin

SYNTHETIC_CREDENTIALS = {
    "name": "Test administrator",
    "username": "test-admin",
    "password": "synthetic-test-password",
}


async def test_creates_owner_and_completes_onboarding(hass):
    hass.auth = await auth.auth_manager_from_config(
        hass, [{"type": "homeassistant"}], []
    )
    assert await initialize_admin(hass, SYNTHETIC_CREDENTIALS)
    owner = await hass.auth.async_get_owner()
    assert owner.is_owner and owner.is_admin
    provider = hass.auth.get_auth_provider("homeassistant", None)
    await provider.async_validate_login("test-admin", SYNTHETIC_CREDENTIALS["password"])
    store = OnboardingStorage(hass, STORAGE_VERSION, STORAGE_KEY, private=True)
    assert set((await store.async_load())["done"]) == set(STEPS)


async def test_rerun_preserves_existing_account_and_password(hass):
    hass.auth = await auth.auth_manager_from_config(
        hass, [{"type": "homeassistant"}], []
    )
    await initialize_admin(hass, SYNTHETIC_CREDENTIALS)
    old_owner = await hass.auth.async_get_owner()
    before = await hass.auth.async_get_users()
    assert not await initialize_admin(
        hass, {**SYNTHETIC_CREDENTIALS, "password": "different-test-password"}
    )
    assert (await hass.auth.async_get_owner()).id == old_owner.id
    assert len(await hass.auth.async_get_users()) == len(before)
    provider = hass.auth.get_auth_provider("homeassistant", None)
    await provider.async_validate_login("test-admin", SYNTHETIC_CREDENTIALS["password"])
    with pytest.raises(InvalidAuth):
        await provider.async_validate_login("test-admin", "different-test-password")


def test_private_credential_file(tmp_path, capsys):
    path = tmp_path / "credentials.json"
    path.write_text(json.dumps(SYNTHETIC_CREDENTIALS))
    assert read_credentials(path) == SYNTHETIC_CREDENTIALS
    assert path.stat().st_mode & 0o777 == 0o600
    assert SYNTHETIC_CREDENTIALS["password"] not in capsys.readouterr().out


@pytest.mark.parametrize(
    "data", [{}, {**SYNTHETIC_CREDENTIALS, "password": ""}, ["bad"], "not-json"]
)
def test_incomplete_credentials_not_echoed(tmp_path, data):
    path = tmp_path / "credentials.json"
    path.write_text(json.dumps(data))
    with pytest.raises(DevelopmentError) as error:
        read_credentials(path)
    assert SYNTHETIC_CREDENTIALS["password"] not in str(error.value)


def test_bootstrap_password_only_in_stdin(tmp_path):
    with patch(
        "scripts.dev.compose",
        return_value=subprocess.CompletedProcess(
            [], 0, '{"created_admin": true, "onboarded": true}'
        ),
    ) as run:
        bootstrap_admin(tmp_path, SYNTHETIC_CREDENTIALS)
    assert SYNTHETIC_CREDENTIALS["password"] not in str(run.call_args.args)
    assert json.loads(run.call_args.kwargs["input"]) == SYNTHETIC_CREDENTIALS


def test_reset_rejects_unmanaged_directory(tmp_path):
    config = tmp_path / "config"
    config.mkdir()
    sentinel = config / "keep-me"
    sentinel.write_text("existing state")
    with pytest.raises(DevelopmentError):
        prepare(tmp_path, 18124, reset=True)
    assert sentinel.read_text() == "existing state"
