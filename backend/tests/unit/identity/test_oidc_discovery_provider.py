import time
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx
from joserfc import jwt
from joserfc.jwk import RSAKey

from sportintel.modules.identity.application.ports import OidcError
from sportintel.modules.identity.infrastructure.oidc_google import DiscoveryOidcProvider

ISS = "https://idp.example.com"
KEY = RSAKey.generate_key(2048, parameters={"kid": "k1", "use": "sig", "alg": "RS256"})
DISCOVERY = {
    "issuer": ISS,
    "authorization_endpoint": f"{ISS}/auth",
    "token_endpoint": f"{ISS}/token",
    "jwks_uri": f"{ISS}/jwks",
}


def id_token(**claims: object) -> str:
    now = int(time.time())
    base = {
        "iss": ISS,
        "aud": "client-1",
        "sub": "s-1",
        "email": "ana@corp.com",
        "email_verified": True,
        "name": "Ana",
        "hd": "corp.com",
        "nonce": "n-1",
        "iat": now,
        "exp": now + 300,
    }
    return jwt.encode({"alg": "RS256", "kid": "k1"}, {**base, **claims}, KEY)


@pytest.fixture
def idp() -> respx.MockRouter:
    with respx.mock(assert_all_called=False) as router:
        router.get(f"{ISS}/.well-known/openid-configuration").respond(json=DISCOVERY)
        router.get(f"{ISS}/jwks").respond(json={"keys": [KEY.as_dict(private=False)]})
        yield router


def provider(domains: frozenset[str] = frozenset({"corp.com"})) -> DiscoveryOidcProvider:
    return DiscoveryOidcProvider(ISS, "client-1", "secret", domains)


async def test_authorize_url_pkce_s256_and_hd(idp: respx.MockRouter) -> None:
    url = await provider().build_authorize_url("st", "n-1", "v" * 64, "http://app/auth/callback")
    q = parse_qs(urlparse(url).query)
    assert q["code_challenge_method"] == ["S256"]
    assert q["code_challenge"][0] != "v" * 64
    assert (q["state"], q["nonce"], q["hd"], q["prompt"]) == (
        ["st"],
        ["n-1"],
        ["corp.com"],
        ["select_account"],
    )
    assert q["scope"] == ["openid email profile"]


async def test_no_hd_with_several_domains(idp: respx.MockRouter) -> None:
    url = await provider(frozenset({"a.com", "b.com"})).build_authorize_url(
        "s", "n", "v" * 64, "http://x"
    )
    assert "hd" not in parse_qs(urlparse(url).query)


async def test_exchange_code_verifies_id_token(idp: respx.MockRouter) -> None:
    token_route = idp.post(f"{ISS}/token").respond(
        json={"access_token": "a", "token_type": "Bearer", "id_token": id_token()}
    )
    who = await provider().exchange_code("code-1", "v" * 64, "http://app/auth/callback", "n-1")
    assert (who.subject, who.email, who.email_verified, who.hosted_domain) == (
        "s-1",
        "ana@corp.com",
        True,
        "corp.com",
    )
    body = parse_qs(token_route.calls[0].request.content.decode())
    assert body["code_verifier"] == ["v" * 64]


@pytest.mark.parametrize(
    "claims",
    [
        {"nonce": "other"},
        {"aud": "someone-else"},
        {"iss": "https://evil"},
        {"exp": int(time.time()) - 3600},
    ],
)
async def test_bad_id_token_rejected(idp: respx.MockRouter, claims: dict[str, object]) -> None:
    idp.post(f"{ISS}/token").respond(
        json={"access_token": "a", "token_type": "Bearer", "id_token": id_token(**claims)}
    )
    with pytest.raises(OidcError):
        await provider().exchange_code("c", "v" * 64, "http://x", "n-1")


async def test_foreign_signature_rejected(idp: respx.MockRouter) -> None:
    other = RSAKey.generate_key(2048, parameters={"kid": "k1"})
    forged = jwt.encode(
        {"alg": "RS256", "kid": "k1"},
        {
            "iss": ISS,
            "aud": "client-1",
            "sub": "s",
            "email": "e@x",
            "nonce": "n-1",
            "exp": int(time.time()) + 60,
        },
        other,
    )
    idp.post(f"{ISS}/token").respond(
        json={"access_token": "a", "token_type": "Bearer", "id_token": forged}
    )
    with pytest.raises(OidcError):
        await provider().exchange_code("c", "v" * 64, "http://x", "n-1")


async def test_token_endpoint_failure_is_oidc_error(idp: respx.MockRouter) -> None:
    idp.post(f"{ISS}/token").mock(side_effect=httpx.ConnectTimeout("t"))
    with pytest.raises(OidcError):
        await provider().exchange_code("c", "v" * 64, "http://x", "n-1")


async def test_stale_discovery_used_when_refresh_fails(idp: respx.MockRouter) -> None:
    p = provider()
    await p.build_authorize_url("s", "n", "v" * 64, "http://x")
    p._fetched_at = 0.0  # кэш устарел
    idp.get(f"{ISS}/.well-known/openid-configuration").mock(side_effect=httpx.ConnectError("down"))
    assert (await p.build_authorize_url("s", "n", "v" * 64, "http://x")).startswith(f"{ISS}/auth")


async def test_discovery_down_without_cache(idp: respx.MockRouter) -> None:
    idp.get(f"{ISS}/.well-known/openid-configuration").mock(side_effect=httpx.ConnectError("down"))
    with pytest.raises(OidcError):
        await provider().build_authorize_url("s", "n", "v" * 64, "http://x")
