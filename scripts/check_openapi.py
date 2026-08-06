from __future__ import annotations

import json
from pathlib import Path

from tradesentinel.api.app import create_app
from tradesentinel.platform.config import Settings

expected = json.loads(Path("packages/contracts/openapi.json").read_text(encoding="utf-8"))
actual = create_app(Settings(environment="test")).openapi()
if actual != expected:
    raise SystemExit("OpenAPI contract drift detected; run pnpm contracts:generate")
