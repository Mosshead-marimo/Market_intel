# ADR 0004: Redis-Based Event System

## Status

Accepted for MVP

## Decision

Use an in-process event bus for local execution and Redis Streams for cross-process events.

## Rationale

This provides loose coupling without introducing Kafka during the MVP.
