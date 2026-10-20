import pytest
from fastapi import HTTPException

from app.rate_limit import AiRateLimiter


def test_per_minute_limit_then_recovers(monkeypatch):
    monkeypatch.setenv("AI_RATE_PER_MINUTE", "2")
    monkeypatch.setenv("AI_DAILY_LIMIT", "100")
    limiter = AiRateLimiter()
    limiter.check("a", now=0)
    limiter.check("a", now=1)
    with pytest.raises(HTTPException) as caught:
        limiter.check("a", now=2)
    assert caught.value.status_code == 429 and int(caught.value.headers["Retry-After"]) >= 1
    limiter.check("b", now=2)
    limiter.check("a", now=61)


def test_daily_limit(monkeypatch):
    monkeypatch.setenv("AI_RATE_PER_MINUTE", "0")
    monkeypatch.setenv("AI_DAILY_LIMIT", "3")
    limiter = AiRateLimiter()
    for stamp in (0, 100, 200):
        limiter.check("a", now=stamp)
    with pytest.raises(HTTPException):
        limiter.check("a", now=300)
    limiter.check("a", now=86401)
