# Contributing

Feature HTTP routes belong in the owning module and are exposed through the manifest `api_router` entrypoint. They must call the execution pipeline and must not access repositories or external clients directly. Shared API files must not contain feature capability names.

Repository-backed modules should inject a concrete module-local factory from the generic `PersistenceResources`; composition-root conditionals for individual modules are prohibited.

## Workflow

1. Select one roadmap task.
2. Read the relevant documentation.
3. Confirm contracts and module boundaries.
4. Implement the smallest complete change.
5. Add or update tests.
6. Run all required checks.
7. Update documentation.
8. Create an ADR for significant architectural decisions.

## Branch Naming

- `feature/<name>`
- `fix/<name>`
- `docs/<name>`
- `refactor/<name>`

## Commit Guidance

Use clear, scoped commits such as:

- `feat(sentiment): add public sentiment capability`
- `fix(market-data): handle stale quote provider response`
- `docs(architecture): document workflow failure policy`

## Pull Request Requirements

Every pull request should include:

- Purpose
- Architecture impact
- Tests added
- Commands run
- Known limitations
- Documentation changes

## Foundation checks

Before opening a pull request, run the backend formatting, lint, strict typing, architecture, and test commands plus the frontend formatting, lint, typing, tests, production build, and contract-drift check listed in `README.md`. Behavior changes require contract and documentation updates; significant boundary changes require an ADR.
