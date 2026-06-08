"""GaaS sidecar bridge — lazy tenant registration with KeyringStore."""

from __future__ import annotations

import logging
from functools import lru_cache

from maref.gaas.api import router as gaas_router
from maref.gaas.api import get_tenant_manager
from maref.gaas.tenant import Tenant
from maref.security.keyring_store import KeyringStore

logger = logging.getLogger(__name__)

_KEYRING_SERVICE = "maref-sidecar"
_KEYRING_KEY = "gaas-hook-api-key"


@lru_cache(maxsize=1)
def _get_hook_api_key() -> str:
    """Lazily register hook tenant and return API key.

    Uses KeyringStore instead of flat file. Only calls
    get_tenant_manager().register() on first invocation.
    """
    store = KeyringStore(_KEYRING_SERVICE)
    cached = store.get(_KEYRING_KEY)
    if cached:
        return cached

    tm = get_tenant_manager()
    hook_tenant = Tenant(tenant_id="maref_hook", name="MAREF Git Hook", tier="pro")
    api_key = tm.register(hook_tenant)
    store.set(_KEYRING_KEY, api_key)
    logger.info("Registered GaaS hook tenant and stored API key in keyring")
    return api_key


def get_hook_api_key() -> str:
    """Public accessor — triggers lazy registration on first call."""
    return _get_hook_api_key()


router = gaas_router
