"""Source text of the HTTP API, for contract tests that check what the routes do.

The routes live in backend/app/main.py, api_common.py and routers/*.py; routers are
included into the app, so `@router.get(...)` reads as `@app.get(...)` here.
"""

import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "backend" / "app"


def api_source() -> str:
    files = [APP / "main.py", APP / "api_common.py", *sorted((APP / "routers").glob("*.py"))]
    text = "\n".join(path.read_text(encoding="utf-8") for path in files)
    return re.sub(r"@router\.(get|post|put|delete)\(", r"@app.\1(", text)
