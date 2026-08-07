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
