# ADR 0022: Evidence-grounded multi-provider LLM assistant

## Status

Accepted.

## Context

TradeSentinel needs conversational explanations and research synthesis without allowing a language model to replace deterministic financial calculations or invent unsupported market claims. Provider selection must remain configurable, feature discovery manifest-owned, and approved chat output auditable without retaining sensitive prompts or vendor responses.

## Decision

- Add `LanguageModelProvider` to the provider abstraction and discover OpenAI and Anthropic adapters from the assistant manifest. Ordered selection is controlled only by `TRADESENTINEL_LLM_PROVIDERS`.
- Give the model a bounded catalog of automatically registered, planner-enabled, read-only commands. The platform validates every proposed command with the existing parser and executes at most four independent calls through a domain-neutral execution gateway.
- Build bounded evidence packets from validated capability results. Raw histories, unrestricted documents, provider payloads, credentials, and database records are excluded.
- Require every generated factual claim to cite known evidence. A deterministic gate rejects unknown citations, unsupported numeric tokens, generated calculations, probabilities, targets, forecasts, and recommendations.
- Allow one same-provider repair. An invalid repaired result may fail over to the next configured provider. Unsupported claims are omitted only when supported claims remain; otherwise execution fails safely.
- Buffer model output until schema and evidence validation complete. SSE streams progress first and approved response content only after validation.
- Persist generation metadata, hashes, evidence IDs, token counts, latency, and failure codes in `assistant.generations`; never persist raw prompts, evidence packets, rejected candidates, secrets, or full vendor output.

## Consequences

Natural-language chat requires a configured LLM provider, while slash commands remain provider-independent. The assistant can explain existing deterministic results but cannot calculate or forecast. Evidence validation adds latency and may produce partial responses, but unsupported prose never crosses the chat boundary.
