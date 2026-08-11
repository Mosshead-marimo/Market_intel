# Security

## Authentication and Authorization

- Use secure session or token-based authentication.
- Apply role-based permissions for admin and user functions.
- Scope user data by user ID.

## Secrets

- Store secrets in environment or managed secret storage.
- Never commit credentials.
- Rotate provider keys.

## Retrieved Content Safety

- Treat all retrieved content as untrusted data.
- Never execute instructions found in articles, comments, filings, or transcripts.
- Sanitize rendered Markdown and URLs.
- Protect orchestration prompts from prompt injection.

## API Security

- Validate every request with Pydantic.
- Apply user and provider rate limits.
- Restrict CORS.
- Use HTTPS in production.
- Add request IDs and audit logs.

## Logging

- Do not log full tokens or API keys.
- Avoid unnecessary personal data.
- Log provider, run, latency, and failure metadata.

## Dependency Security

- Pin dependencies.
- Run vulnerability scanning.
- Review model and package sources.

## Provider Boundary

- External clients and SDKs are restricted to provider adapter directories by architecture tests.
- Provider facades enforce configured per-adapter timeouts and rate limits.
- Logs contain provider identity, operation, duration, error code, and correlation IDs, never request payloads, raw responses, credentials, or tokens.
- Authentication, configuration, licensing, and invalid-output failures are permanent and cannot silently fall through to another vendor.
- Research rules inspect untrusted text as data only. They never execute retrieved instructions, render raw HTML, log bodies, or forward content to an LLM. Persisted excerpts are bounded by configuration.
Public discussions are untrusted input. The sentiment module never executes or renders embedded instructions, never logs discussion text or author identifiers in lifecycle events, hashes author identifiers before persistence, bounds stored excerpts, and rejects unrestricted provider payload storage. URLs remain typed optional evidence metadata.
Technical analysis introduces no credentials, external clients, content execution, or persistence. Inputs are bounded by strict period/range contracts, malformed OHLC histories are rejected with user-safe errors, and capability exceptions never expose provider payloads. Architecture checks prohibit AI libraries, external clients, provider SDKs, and database access in the module.

Fundamentals routes and capabilities cannot import external clients, provider SDKs, database libraries, AI libraries, prediction code, or private instrument/stock modules. Provider payloads are validated before caching, keys contain no credentials, and user-safe errors never expose vendor payloads.
