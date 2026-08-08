# Module System

## Objective

Adding a new feature should require creating one isolated module, registering it, and optionally adding it to a workflow.

## Standard Capability Contract

```python
from abc import ABC, abstractmethod
from typing import Any


class Capability(ABC):
    name: str
    version: str
    description: str
    commands: list[str]
    intents: list[str]
    dependencies: list[str]
    permissions: list[str]

    @abstractmethod
    async def execute(
        self,
        context: "ExecutionContext",
        payload: dict[str, Any],
    ) -> "CapabilityResult": ...
```

## Standard Result

```python
class CapabilityResult:
    capability: str
    status: str
    data: dict
    summary: str | None
    sources: list
    warnings: list[str]
    metadata: dict
```

## Module Manifest

```yaml
name: public_sentiment
version: 1.0.0
description: Measures public sentiment and narrative shifts
commands:
  - /public-sentiment
  - /sentiment-trend
intents:
  - public_sentiment_analysis
dependencies:
  - instrument.resolve
  - news.research
provides:
  - sentiment_snapshot
  - narrative_summary
events:
  consumes:
    - research.document.collected
  produces:
    - sentiment.analysis.completed
```

## Standard Module Structure

```text
modules/public_sentiment/
├── manifest.yaml
├── capability.py
├── commands.py
├── schemas.py
├── service.py
├── repository.py
├── providers/
├── prompts/
├── tests/
└── migrations/
```

## Module Rules

- Modules may not import private implementation files from another module.
- Modules communicate through shared contracts, events, or capability calls.
- Provider SDKs must remain in adapter folders.
- Database writes are restricted to module-owned schemas.
- Every module must support typed errors and warnings.
- Every module must expose health and observability metadata.

## Adding a New Feature

1. Create the module directory.
2. Add a manifest.
3. Define input and output contracts.
4. Implement the capability.
5. Register commands and intents.
6. Add providers if required.
7. Add persistence if required.
8. Add response components.
9. Add tests.
10. Add to workflows when relevant.
11. Update documentation.

## Foundation Loading Convention

Production modules live below `tradesentinel.modules`. The loader recursively discovers `manifest.yaml` files below configured roots. A new capability requires only the manifest declaration and a concrete capability class; there is no `plugin.py`, registration function, module list, or core conditional.

```yaml
name: example.module
version: 1.0.0
description: Example module
capabilities:
  - name: example.run
    class_path: tradesentinel.modules.example.capability:ExampleCapability
    description: Runs the example
    idempotent: true
    retry:
      max_attempts: 3
commands:
  - name: /example
    description: Run the example
    target:
      kind: capability
      name: example.run
intents:
  - name: example_request
    description: Run the example
    examples: ["run the example"]
    target:
      kind: capability
      name: example.run
```

An optional provider declaration exposes a module-local adapter without registering it in core code:

```yaml
providers:
  - kind: market_data
    name: vendor_name
    class_path: tradesentinel.modules.example.providers.adapters.vendor:VendorMarketData
    timeout_ms: 10000
    rate_limit:
      requests: 60
      window_seconds: 60
```

The class must implement the interface associated with its declared kind. Provider declarations are staged before capability construction, allowing a capability to request `MarketDataProvider`, `NewsProvider`, `SentimentProvider`, `EconomicDataProvider`, or `FundamentalsProvider` through its typed constructor. The module still requires at least one capability; provider-only modules are not features.

Modules may declare `api_router: package.module:router`. The API adapter validates that the entrypoint exposes a FastAPI `APIRouter` and includes routers in deterministic manifest order. Routes remain thin and execute their own registered capabilities through the shared pipeline; the platform loader never imports FastAPI or feature routers.

`stock_market_data` demonstrates a required provider port: discovery and startup succeed without an adapter through a typed unavailable facade, while execution returns `PROVIDER_NOT_CONFIGURED`. Commands target declarative resolution workflows and the module router exposes structured capability inputs without central API conditionals.

`research` follows the same lazy news-provider boundary. Its manifest registers search, deduplication, extraction, timeline, report, and evidence capabilities plus two workflows and module-owned routes. The service applies versioned deterministic rules and writes only through its repository to the `research` schema; no platform or central API code names a research target.

The manifest owns registration metadata. A capability class owns only its input model and async execution method. Annotated constructor dependencies are resolved from registered platform ports or recursively constructed module-private concrete services; unresolved, untyped, abstract, or cyclic dependencies fail startup.

Discovery order is deterministic and registration is atomic. Commands, intents, workflows, and event consumers are generated from manifests after the complete capability graph validates. `platform.system` is the executable reference and contains no market logic.

Intent declarations use `match: exact` with examples or declare the single application-wide `match: fallback`. `input_field` binds original natural-language text into the target payload. Startup rejects multiple fallbacks, so core code never owns a default feature target.
