"""JWT authentication module: HS256 key provider, middleware, dependencies.

The middleware verifies tokens symmetrically with a shared secret issued by
POSBackend (HS256). ``JWKSFetcher`` / ``get_jwks_fetcher`` are kept as
backward-compatible aliases so existing imports keep working.
"""

from __future__ import annotations

import logging

from app.config import settings

logger = logging.getLogger(__name__)


class HS256KeyProvider:
    """Provides the shared symmetric secret used for HS256 verification.

    Simple provider: returns ``settings.JWT_SHARED_SECRET``. No network,
    no caching, no rotation concerns.
    """

    def __init__(self, secret: str = "") -> None:
        self._secret = secret

    @property
    def secret(self) -> str:
        """The shared secret used to verify HS256 tokens."""
        return self._secret or settings.JWT_SHARED_SECRET

    @property
    def healthy(self) -> bool:
        """True if a shared secret is configured."""
        return bool(self._secret or settings.JWT_SHARED_SECRET)


# Module-level singleton
_key_provider: HS256KeyProvider | None = None


def get_key_provider() -> HS256KeyProvider:
    """Return the module-level HS256 key provider singleton."""
    global _key_provider
    if _key_provider is None:
        _key_provider = HS256KeyProvider(secret=settings.JWT_SHARED_SECRET)
    return _key_provider


# ── Backward-compatible aliases ──────────────────────────────────────────────
# Used by app/auth/router.py (health) and existing tests. No longer JWKS-based.

JWKSFetcher = HS256KeyProvider
_jwks_fetcher: HS256KeyProvider | None = None


def get_jwks_fetcher() -> HS256KeyProvider:
    """Backward-compatible alias for ``get_key_provider``.

    Kept to avoid import breakage; returns the HS256 key provider.
    """
    return get_key_provider()
