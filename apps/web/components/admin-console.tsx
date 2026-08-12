"use client";

import { Activity, Database, RefreshCw, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { FormEvent, useCallback, useState } from "react";
import type { MarketShiftWatchlist } from "@tradesentinel/contracts";
import { getCapabilities, getHealth } from "@/lib/api";
import {
  ingestMarketShiftObservations,
  loadMarketShiftWatchlist,
  loadPredictionAdmin,
  runMarketShiftSchedule,
} from "@/lib/workspace-api";
import { WorkspaceNav } from "./workspace-nav";
import { TokenGate } from "./token-gate";

export function AdminHome() {
  const [status, setStatus] = useState<string>("Not checked");
  const inspect = useCallback(() => {
    setStatus("Checking…");
    void Promise.all([getHealth(), getCapabilities()])
      .then(([health, capabilities]) =>
        setStatus(
          `${health.status} · ${capabilities.length} registered capabilities`,
        ),
      )
      .catch(() => setStatus("Runtime unavailable"));
  }, []);
  return (
    <main className="workspace-shell">
      <WorkspaceNav current="admin" />
      <section className="admin-home">
        <span className="eyebrow">Operations</span>
        <h1>Runtime administration</h1>
        <p>
          Provider selection remains environment-owned. Administrative tokens
          are held only in memory and cleared on refresh.
        </p>
        <div className="admin-grid">
          <article>
            <Activity />
            <h2>Platform runtime</h2>
            <p>{status}</p>
            <button onClick={inspect}>
              <RefreshCw size={15} />
              Inspect status
            </button>
          </article>
          <Link href="/admin/market-shift">
            <RefreshCw />
            <h2>Market Shift</h2>
            <p>
              Ingest point-in-time observations and inspect the scheduled
              watchlist.
            </p>
          </Link>
          <Link href="/admin/prediction">
            <Database />
            <h2>Prediction engine</h2>
            <p>Internal model registry and persisted prediction operations.</p>
          </Link>
        </div>
      </section>
    </main>
  );
}

export function MarketShiftAdmin() {
  return (
    <main className="workspace-shell">
      <WorkspaceNav current="admin" />
      <TokenGate title="Market Shift administration">
        {(token) => <MarketShiftAdminPanel token={token} />}
      </TokenGate>
    </main>
  );
}
function MarketShiftAdminPanel({ token }: { token: string }) {
  const [watchlist, setWatchlist] = useState<MarketShiftWatchlist | null>(null);
  const [payload, setPayload] = useState(
    '{\n  "idempotency_key": "batch-1",\n  "observations": []\n}',
  );
  const [message, setMessage] = useState<string | null>(null);
  const refresh = useCallback(() => {
    setMessage("Loading…");
    void loadMarketShiftWatchlist(token)
      .then((value) => {
        setWatchlist(value);
        setMessage(null);
      })
      .catch((cause: unknown) =>
        setMessage(cause instanceof Error ? cause.message : "Request failed."),
      );
  }, [token]);
  const ingest = (event: FormEvent) => {
    event.preventDefault();
    setMessage("Validating and ingesting…");
    try {
      const body: unknown = JSON.parse(payload);
      void ingestMarketShiftObservations(token, body)
        .then(() => setMessage("Observation batch accepted."))
        .catch((cause: unknown) =>
          setMessage(
            cause instanceof Error ? cause.message : "Ingestion failed.",
          ),
        );
    } catch {
      setMessage("The observation batch is not valid JSON.");
    }
  };
  return (
    <section className="admin-workspace">
      <header>
        <div>
          <span className="eyebrow">Market Shift</span>
          <h1>Evidence ingestion and schedules</h1>
        </div>
        <div className="admin-toolbar">
          <button onClick={refresh}>
            <RefreshCw size={16} />
            Load watchlist
          </button>
          <button
            onClick={() => {
              setMessage("Running due schedules…");
              void runMarketShiftSchedule(token)
                .then(({ processed }) =>
                  setMessage(`${processed} due calculation(s) processed.`),
                )
                .catch((cause: unknown) =>
                  setMessage(
                    cause instanceof Error ? cause.message : "Schedule failed.",
                  ),
                );
            }}
          >
            <Activity size={16} />
            Run due now
          </button>
        </div>
      </header>
      {message && (
        <p className="admin-message" role="status">
          {message}
        </p>
      )}
      <div className="admin-columns">
        <section className="analysis-card">
          <h2>Normalized observation batch</h2>
          <p>
            Values must match metric names, units, and point-in-time rules from
            the versioned scoring configuration.
          </p>
          <form onSubmit={ingest}>
            <textarea
              value={payload}
              onChange={(event) => setPayload(event.target.value)}
              rows={18}
              spellCheck={false}
            />
            <button type="submit">
              <ShieldCheck size={16} />
              Validate and ingest
            </button>
          </form>
        </section>
        <section className="analysis-card">
          <h2>Daily watchlist</h2>
          {watchlist ? (
            watchlist.items.length ? (
              <ul className="admin-list">
                {watchlist.items.map((item) => (
                  <li key={item.watchlist_id}>
                    <strong>
                      {item.instrument.symbol} · {item.instrument.exchange}
                    </strong>
                    <span>
                      {item.enabled ? "Enabled" : "Disabled"} · {item.run_time}{" "}
                      {item.timezone}
                    </span>
                    <small>
                      Next{" "}
                      {item.next_run_at
                        ? new Date(item.next_run_at).toLocaleString()
                        : "on worker poll"}
                    </small>
                  </li>
                ))}
              </ul>
            ) : (
              <p>No instruments are scheduled.</p>
            )
          ) : (
            <p>Load the protected watchlist to inspect schedules.</p>
          )}
        </section>
      </div>
    </section>
  );
}

export function PredictionAdmin() {
  return (
    <main className="workspace-shell">
      <WorkspaceNav current="admin" />
      <TokenGate title="Prediction engine administration">
        {(token) => <PredictionAdminPanel token={token} />}
      </TokenGate>
    </main>
  );
}
function PredictionAdminPanel({ token }: { token: string }) {
  const [resource, setResource] = useState<"models" | "predictions">("models");
  const [items, setItems] = useState<Record<string, unknown>[]>([]);
  const [message, setMessage] = useState(
    "Select a resource to load internal records.",
  );
  const load = () => {
    setMessage("Loading protected records…");
    void loadPredictionAdmin(token, resource)
      .then((page) => {
        setItems(page.items);
        setMessage(`${page.items.length} ${resource} loaded.`);
      })
      .catch((cause: unknown) =>
        setMessage(cause instanceof Error ? cause.message : "Request failed."),
      );
  };
  return (
    <section className="admin-workspace">
      <header>
        <div>
          <span className="eyebrow">Internal ML only</span>
          <h1>Prediction registry</h1>
          <p>
            These records are not imported into chat or normal user workspaces.
          </p>
          <Link href="/model-performance" className="admin-inline-link">
            Open model performance
          </Link>
        </div>
      </header>
      <div className="admin-toolbar">
        <select
          value={resource}
          onChange={(event) =>
            setResource(event.target.value as "models" | "predictions")
          }
        >
          <option value="models">Model registry</option>
          <option value="predictions">Prediction history</option>
        </select>
        <button onClick={load}>
          <RefreshCw size={16} />
          Load
        </button>
      </div>
      <p className="admin-message">{message}</p>
      <div className="record-grid">
        {items.map((item, index) => (
          <article
            key={String(item.model_version ?? item.prediction_id ?? index)}
          >
            <pre>{JSON.stringify(item, null, 2)}</pre>
          </article>
        ))}
      </div>
    </section>
  );
}
