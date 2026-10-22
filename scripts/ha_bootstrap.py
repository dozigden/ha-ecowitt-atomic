"""Create the development HA administrator.

Run inside the HA container with the server stopped and credentials on stdin.
"""

import asyncio
import json
import sys

from homeassistant import bootstrap, loader
from homeassistant.auth.const import GROUP_ID_ADMIN
from homeassistant.components.onboarding import (
    STORAGE_KEY,
    STORAGE_VERSION,
    OnboardingStorage,
)
from homeassistant.components.onboarding.const import STEPS
from homeassistant.core import HomeAssistant


async def initialize_admin(hass: HomeAssistant, credentials: dict[str, str]) -> bool:
    """Keep an existing owner; create one only on first setup."""
    owner = await hass.auth.async_get_owner()
    created = owner is None
    if created:
        provider = hass.auth.get_auth_provider("homeassistant", None)
        if provider is None:
            raise RuntimeError("The local HA authentication provider is unavailable")
        await provider.async_initialize()
        await provider.async_add_auth(credentials["username"], credentials["password"])
        owner = await hass.auth.async_create_user(
            credentials["name"], group_ids=[GROUP_ID_ADMIN]
        )
        login = await provider.async_get_or_create_credentials(
            {"username": credentials["username"]}
        )
        await hass.auth.async_link_user(owner, login)
        await provider.async_validate_login(
            credentials["username"], credentials["password"]
        )
        if not owner.is_owner or not owner.is_admin:
            raise RuntimeError("The development account is not an owner/admin")
    store = OnboardingStorage(hass, STORAGE_VERSION, STORAGE_KEY, private=True)
    await store.async_save({"done": list(STEPS)})
    return created


async def initialize(credentials: dict[str, str]) -> bool:
    """Start HA, initialize authentication, and flush storage."""
    directory = "/config"
    sys.path.insert(0, directory)
    hass = HomeAssistant(directory)
    loader.async_setup(hass)
    try:
        if (
            await bootstrap.async_from_config_dict(
                {"homeassistant": {"time_zone": "UTC"}}, hass
            )
            is None
        ):
            raise RuntimeError("HA initialization failed")
        await hass.async_start()
        return await initialize_admin(hass, credentials)
    finally:
        await hass.async_stop()


def main() -> None:
    """Read credentials from stdin and report setup status."""
    try:
        credentials = json.load(sys.stdin)
        created = asyncio.run(initialize(credentials))
    except Exception:  # noqa: BLE001
        # Exceptions may contain credentials.
        print(json.dumps({"error": "HA administrator initialization failed"}))
        raise SystemExit(1) from None
    print(json.dumps({"created_admin": created, "onboarded": True}))


if __name__ == "__main__":
    main()
