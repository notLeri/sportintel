"""OIDC-провайдер по discovery (по умолчанию Google Workspace, CONV §1)."""

import time
from typing import Any

import structlog
from authlib.integrations.httpx_client import AsyncOAuth2Client
from joserfc import jwt
from joserfc.errors import JoseError
from joserfc.jwk import KeySet

from sportintel.modules.identity.application.ports import OidcError
from sportintel.modules.identity.domain.access_policy import OidcIdentity

DISCOVERY_TTL_S = 3600.0
TIMEOUT_S = 10.0
LEEWAY_S = 60
_log = structlog.get_logger("sportintel.identity.oidc")


class DiscoveryOidcProvider:
    def __init__(
        self,
        issuer: str,
        client_id: str,
        client_secret: str,
        allowed_domains: frozenset[str] = frozenset(),
    ) -> None:
        self.issuer = issuer.rstrip("/")
        self.client_id = client_id
        self._client_secret = client_secret
        self._hd = next(iter(allowed_domains)) if len(allowed_domains) == 1 else None
        self._discovery: dict[str, Any] | None = None
        self._jwks: KeySet | None = None
        self._fetched_at = 0.0

    def _client(self) -> AsyncOAuth2Client:
        return AsyncOAuth2Client(
            client_id=self.client_id,
            client_secret=self._client_secret,
            code_challenge_method="S256",
            timeout=TIMEOUT_S,
        )

    async def _metadata(self) -> tuple[dict[str, Any], KeySet]:
        fresh = time.monotonic() - self._fetched_at < DISCOVERY_TTL_S
        if self._discovery is not None and self._jwks is not None and fresh:
            return self._discovery, self._jwks
        try:
            async with self._client() as c:
                url = f"{self.issuer}/.well-known/openid-configuration"
                discovery = (
                    (await c.request("GET", url, withhold_token=True)).raise_for_status().json()
                )
                jwks_url = discovery["jwks_uri"]
                jwks = (
                    (await c.request("GET", jwks_url, withhold_token=True))
                    .raise_for_status()
                    .json()
                )
            self._discovery, self._jwks = discovery, KeySet.import_key_set(jwks)
            self._fetched_at = time.monotonic()
        except Exception as e:
            if self._discovery is not None and self._jwks is not None:
                # Старый кэш лучше отказа во входе (BE-T0.15 §13).
                _log.warning("identity.oidc_discovery_stale", error=type(e).__name__)
                return self._discovery, self._jwks
            raise OidcError("discovery failed") from e
        return self._discovery, self._jwks

    async def build_authorize_url(
        self, state: str, nonce: str, code_verifier: str, redirect_uri: str
    ) -> str:
        discovery, _ = await self._metadata()
        extra = {"hd": self._hd} if self._hd else {}
        async with self._client() as c:
            url, _ = c.create_authorization_url(
                discovery["authorization_endpoint"],
                state=state,
                code_verifier=code_verifier,
                redirect_uri=redirect_uri,
                nonce=nonce,
                scope="openid email profile",
                prompt="select_account",
                **extra,
            )
        return str(url)

    async def exchange_code(
        self, code: str, code_verifier: str, redirect_uri: str, nonce: str
    ) -> OidcIdentity:
        discovery, keys = await self._metadata()
        try:
            async with self._client() as c:
                token = await c.fetch_token(
                    discovery["token_endpoint"],
                    code=code,
                    code_verifier=code_verifier,
                    redirect_uri=redirect_uri,
                )
            id_token = token["id_token"]
            decoded = jwt.decode(id_token, keys)
            jwt.JWTClaimsRegistry(
                leeway=LEEWAY_S,
                iss={"essential": True, "value": discovery.get("issuer", self.issuer)},
                aud={"essential": True, "value": self.client_id},
                exp={"essential": True},
                nonce={"essential": True, "value": nonce},
            ).validate(decoded.claims)
        except (JoseError, KeyError, ValueError) as e:
            raise OidcError(f"invalid id_token: {type(e).__name__}") from e
        except Exception as e:  # сеть, таймаут, ошибка IdP
            raise OidcError(f"token exchange failed: {type(e).__name__}") from e
        claims = decoded.claims
        if not claims.get("sub") or not claims.get("email"):
            raise OidcError("id_token without sub/email")
        return OidcIdentity(
            subject=str(claims["sub"]),
            email=str(claims["email"]),
            email_verified=claims.get("email_verified") is True,
            name=str(claims.get("name") or ""),
            hosted_domain=claims.get("hd"),
        )

    async def end_session_url(self) -> str | None:
        try:
            discovery, _ = await self._metadata()
        except OidcError:
            return None
        url = discovery.get("end_session_endpoint")
        return str(url) if url else None
