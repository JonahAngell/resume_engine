from pathlib import Path

POLICY = (Path(__file__).resolve().parents[1] / ".launch/opa/authz.rego").read_text(
    encoding="utf-8"
)


def test_default_deny_and_exact_health_exception():
    assert "default allow := false" in POLICY
    assert 'input.request.method == "GET"' in POLICY
    assert 'input.request.path == "/health"' in POLICY
    assert "input.user.authenticated == true" in POLICY
    assert "startswith" not in POLICY and '"/api"' not in POLICY
