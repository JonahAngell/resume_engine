"""
test_openrouter_key.py

Simple diagnostic for an OpenRouter API key using a free model.
Uses only the Python standard library (no pip installs required).

Usage:
    python test_openrouter_key.py                  # uses OPENROUTER_MODEL from .env, else openrouter/free
    python test_openrouter_key.py --model <id>     # test a specific :free model
    python test_openrouter_key.py --env path/.env  # use a different .env file
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

API_BASE = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "openrouter/free"
TIMEOUT_SECONDS = 60


def load_env(path):
    """Minimal .env parser: KEY=VALUE lines, ignores comments and blank lines."""
    values = {}
    if not os.path.isfile(path):
        print(f"[ERROR] .env file not found at: {os.path.abspath(path)}")
        sys.exit(1)
    with open(path, "r", encoding="utf-8-sig") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[len("export "):]
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def mask(secret):
    if len(secret) <= 12:
        return "*" * len(secret)
    return f"{secret[:8]}...{secret[-4:]} (length {len(secret)})"


def request(method, url, api_key, body=None):
    """Return (status_code, headers_dict, parsed_json_or_text)."""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("Content-Type", "application/json")
    req.add_header("X-Title", "Resume Engine key test")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            status, headers, raw = resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as err:
        status, headers, raw = err.code, dict(err.headers), err.read()
    except urllib.error.URLError as err:
        print(f"[ERROR] Could not reach OpenRouter: {err.reason}")
        sys.exit(2)
    text = raw.decode("utf-8", errors="replace")
    try:
        return status, headers, json.loads(text)
    except json.JSONDecodeError:
        return status, headers, text


def print_rate_headers(headers):
    found = {k: v for k, v in headers.items()
             if k.lower().startswith("x-ratelimit") or k.lower() == "retry-after"}
    if found:
        print("  Rate-limit headers:")
        for key, value in found.items():
            print(f"    {key}: {value}")


def explain_status(status, payload):
    error = payload.get("error", {}) if isinstance(payload, dict) else {}
    metadata = error.get("metadata") or {}
    if status == 401:
        return "Key rejected (401). Check the key value in .env, or regenerate it."
    if status == 402:
        return "Payment required (402). Credit balance may be negative; this also blocks free models."
    if status == 404:
        return "Model not found (404). The model ID may be wrong or no longer free."
    if status == 429:
        if metadata.get("provider_name") or metadata.get("provider_code"):
            return "429 from the upstream provider: the free provider is busy. Try later or another model."
        return "429 from OpenRouter: you have probably hit the free per-minute or per-day limit."
    if status in (502, 503):
        return f"{status}: the upstream provider failed or is overloaded. Retry later."
    return None


def step_check_key(api_key):
    print("\n=== STEP 1: Check key (GET /key) ===")
    status, headers, payload = request("GET", f"{API_BASE}/key", api_key)
    print(f"  HTTP status: {status}")
    if status != 200:
        print(f"  Response: {json.dumps(payload, indent=2) if isinstance(payload, dict) else payload}")
        hint = explain_status(status, payload if isinstance(payload, dict) else {})
        if hint:
            print(f"  -> {hint}")
        return False
    data = payload.get("data", {}) if isinstance(payload, dict) else {}
    for field in ("label", "usage", "limit", "limit_remaining", "is_free_tier"):
        if field in data:
            print(f"  {field}: {data[field]}")
    print("  -> Key is valid.")
    return True


def step_chat(api_key, model):
    print(f"\n=== STEP 2: Send a test prompt (model: {model}) ===")
    body = {
        "model": model,
        "messages": [{"role": "user",
                      "content": "Reply with exactly: OK. Then list 3 skills found in: "
                                 "'Built SQL reports and Python automations in Workday.'"}],
        "max_tokens": 100,
    }
    status, headers, payload = request("POST", f"{API_BASE}/chat/completions", api_key, body)
    print(f"  HTTP status: {status}")
    print_rate_headers(headers)

    if status == 200 and isinstance(payload, dict) and payload.get("choices"):
        choice = payload["choices"][0]
        content = (choice.get("message") or {}).get("content")
        print(f"  Generation ID : {payload.get('id')}")
        print(f"  Model used    : {payload.get('model')}")
        print(f"  Provider      : {payload.get('provider', 'n/a')}")
        print(f"  Finish reason : {choice.get('finish_reason')}")
        print(f"  Token usage   : {payload.get('usage')}")
        if content:
            print(f"  Reply:\n    {content.strip()}")
            print("  -> Success. This request was sent to OpenRouter under your key.")
            return True
        print("  -> 200 returned but the reply was empty (common with some free models).")
        return False

    print("  Response body:")
    print(json.dumps(payload, indent=2) if isinstance(payload, dict) else f"    {payload}")
    hint = explain_status(status, payload if isinstance(payload, dict) else {})
    if hint:
        print(f"  -> {hint}")
    return False


def main():
    parser = argparse.ArgumentParser(description="Test an OpenRouter API key with a free model.")
    parser.add_argument("--env", default=".env", help="Path to .env file (default: ./.env)")
    parser.add_argument("--model", help="Model ID to test (default: OPENROUTER_MODEL or openrouter/free)")
    args = parser.parse_args()

    env = load_env(args.env)
    api_key = env.get("OPENROUTER_API_KEY", "")
    if not api_key:
        print(f"[ERROR] OPENROUTER_API_KEY is missing or empty in {os.path.abspath(args.env)}")
        sys.exit(1)

    model = args.model or env.get("OPENROUTER_MODEL") or DEFAULT_MODEL
    print(f".env file : {os.path.abspath(args.env)}")
    print(f"API key   : {mask(api_key)}")
    if not api_key.startswith("sk-or-"):
        print("  [WARN] Key does not start with 'sk-or-'. Check it was copied correctly.")

    key_ok = step_check_key(api_key)
    chat_ok = step_chat(api_key, model) if key_ok else False

    print("\n=== RESULT ===")
    print(f"  Key valid      : {'YES' if key_ok else 'NO'}")
    print(f"  Model answered : {'YES' if chat_ok else 'NO'}")
    sys.exit(0 if chat_ok else 1)


if __name__ == "__main__":
    main()
