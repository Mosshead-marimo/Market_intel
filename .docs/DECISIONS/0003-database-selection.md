# ADR 0003: PostgreSQL Primary Database

## Status

Accepted

## Decision

Use PostgreSQL as the primary database, with TimescaleDB and pgvector where useful.

## Rationale

The project needs relational integrity, time-series data, semantic retrieval, and mature tooling without operating multiple primary databases.
