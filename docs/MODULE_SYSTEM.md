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

Production modules live below `tradesentinel.modules`. Each `manifest.yaml` declares a `module:function` entrypoint, capability names, commands, intents, provided outputs, and consumed/produced events. The entrypoint returns a `ModuleRegistration` containing already-injected capabilities, command descriptors, workflows, and subscriptions.

Discovery is deterministic and validates all module manifests before registry mutation. A module may compose its own private services and adapters, but it receives shared infrastructure only through public platform ports. `platform.system` is the executable reference implementation and contains no market logic.
