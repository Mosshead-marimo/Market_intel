# ADR 0007: Server-Sent Events for Chat Streaming

## Status

Accepted for MVP

## Decision

Use Server-Sent Events for one-way progress and response streaming from the backend to the web client.

## Rationale

SSE is simpler than WebSockets for the MVP chat workflow and supports status and component events.
