from __future__ import annotations

import json
import sys
from pathlib import Path

from tradesentinel.api.app import create_app
from tradesentinel.platform.config import Settings


def main() -> None:
    destination = Path(sys.argv[1] if len(sys.argv) > 1 else "packages/contracts/openapi.json")
    schema = create_app(Settings(environment="test")).openapi()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
