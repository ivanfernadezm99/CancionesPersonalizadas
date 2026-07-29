"""JWT authentication module: JWKS fetcher, middleware, dependencies."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx
from jose import jwk, jwt
from jose.constants import Algorithms
from jose.exceptions import JWKError, JWSError, JWTError

from app.config import settings

logger = logging.getLogger(__name__)


class JWKSFetcher:
    """Fetch and cache JWKS keys with TTL-based caching and eager refresh.

    Fetches the JWKS endpoint on first access, caches for ``ttl`` seconds,
    and re-fetches immediately if a key lookup fails (handles key rotation).
    """

    def __init__(self, jwks_url: str, ttl: int = 3600) -> None:
        self._jwks_url = jwks_url
        self._ttl = ttl
        self._keys: dict[str, Any] = {}  # kid → RSA public key
        self._last_fetch: float = 0.0
        self._fetch_error: bool = False

    # ── Public API ───────────────────────────────────────────────────────────

    async def get_public_key(self, kid: str) -> dict[str, Any] | None:
        """Get an RSA public key for the given ``kid``.

        Returns the JWK dict or ``None`` if the key is not found.
        Re-fetches on cache miss or when the cache is expired.
        """
        if self._needs_refresh():
            await self._fetch_keys()

        key = self._keys.get(kid)
        if key is not None:
            return key

        # Eager refresh: try fetching again in case keys rotated
        logger.info("Key %s not found in cache, eager-refreshing JWKS", kid)
        await self._fetch_keys()
        return self._keys.get(kid)

    @property
    def healthy(self) -> bool:
        """True if the JWKS endpoint was reachable (ever or on last refresh)."""
        return not self._fetch_error

    # ── Internal ─────────────────────────────────────────────────────────────

    def _needs_refresh(self) -> bool:
        return (time.monotonic() - self._last_fetch) >= self._ttl

    async def _fetch_keys(self) -> None:
        """Fetch and parse JWKS keys from the configured endpoint."""
        if not self._jwks_url:
            logger.warning("JWKS_URL is not configured — skipping key fetch")
            self._fetch_error = True
            return

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(self._jwks_url)
                response.raise_for_status()
                jwks: dict[str, Any] = response.json()
        except httpx.HTTPError as exc:
            logger.error("Failed to fetch JWKS from %s: %s", self._jwks_url, exc)
            self._fetch_error = True
            raise

        keys: dict[str, Any] = {}
        for key_data in jwks.get("keys", []):
            kid = key_data.get("kid")
            if kid:
                try:
                    keys[kid] = jwk.construct(key_data, algorithm=Algorithms.RS256)
                except JWKError as exc:
                    logger.warning("Skipping invalid JWK key %s: %s", kid, exc)

        self._keys = keys
        self._last_fetch = time.monotonic()
        self._fetch_error = False
        logger.info("Fetched %d JWKS keys from %s", len(keys), self._jwks_url)


# Module-level singleton
_jwks_fetcher: JWKSFetcher | None = None


def get_jwks_fetcher() -> JWKSFetcher:
    """Return the module-level JWKS fetcher singleton."""
    global _jwks_fetcher
    if _jwks_fetcher is None:
        _jwks_fetcher = JWKSFetcher(jwks_url=settings.JWT_JWKS_URL)
    return _jwks_fetcher
