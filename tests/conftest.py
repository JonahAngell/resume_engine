import pytest

from app.ai_client import clear_gateway_token

GATEWAY_ENV = (
    "STUDIOSHARE_AI_GATEWAY_URL",
    "STUDIOSHARE_OIDC_TOKEN",
    "STUDIOSHARE_OIDC_URL",
    "STUDIOSHARE_AI_MODELS",
)


@pytest.fixture(autouse=True)
def _no_gateway_from_shell(monkeypatch):
    """Keep `launch env pull` values in a developer shell out of the AI tests."""
    for name in GATEWAY_ENV:
        monkeypatch.delenv(name, raising=False)
    clear_gateway_token()
    yield
    clear_gateway_token()
