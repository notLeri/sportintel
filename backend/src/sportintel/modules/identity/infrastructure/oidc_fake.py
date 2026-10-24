"""FakeOidcProvider для local/ci/e2e и тестов (CONV §13): без сети."""

from urllib.parse import urlencode

from sportintel.modules.identity.application.ports import OidcError
from sportintel.modules.identity.domain.access_policy import OidcIdentity


class FakeOidcProvider:
    """authorize URL ведёт сразу на наш callback; `code` = email (или задан next_identity)."""

    def __init__(self) -> None:
        self.next_identity: OidcIdentity | None = None
        self.fail_with: Exception | None = None
        self.calls: list[dict[str, str]] = []

    async def build_authorize_url(
        self, state: str, nonce: str, code_verifier: str, redirect_uri: str
    ) -> str:
        return f"{redirect_uri}?{urlencode({'code': 'fake@example.com', 'state': state})}"

    async def exchange_code(
        self, code: str, code_verifier: str, redirect_uri: str, nonce: str
    ) -> OidcIdentity:
        self.calls.append({"code": code, "code_verifier": code_verifier, "nonce": nonce})
        if self.fail_with is not None:
            raise self.fail_with
        if self.next_identity is not None:
            return self.next_identity
        if "@" not in code:
            raise OidcError("fake: code must be an email")
        return OidcIdentity(
            subject=f"fake|{code}", email=code, email_verified=True, name="", hosted_domain=None
        )

    async def end_session_url(self) -> str | None:
        return None
