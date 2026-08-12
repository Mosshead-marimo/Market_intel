"use client";

import { ArrowLeft, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import type {
  InstrumentRef,
  MarketShiftHistoryPage,
} from "@tradesentinel/contracts";
import { loadMarketShiftHistory, resolveInstrument } from "@/lib/workspace-api";
import { WorkspaceNav } from "./workspace-nav";

export function MarketShiftHistoryView({
  query,
  exchange,
}: {
  query: string;
  exchange?: string;
}) {
  const [instrument, setInstrument] = useState<InstrumentRef | null>(null);
  const [history, setHistory] = useState<MarketShiftHistoryPage | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    void resolveInstrument(query, exchange)
      .then((resolved) => {
        if (!resolved.match)
          throw new Error("The instrument is not resolved unambiguously.");
        setInstrument(resolved.match.instrument);
        return loadMarketShiftHistory(resolved.match.instrument.instrument_id);
      })
      .then(setHistory)
      .catch((cause: unknown) =>
        setError(cause instanceof Error ? cause.message : "History failed."),
      );
  }, [query, exchange]);
  return (
    <main className="workspace-shell">
      <WorkspaceNav current="workspace" />
      <section className="history-workspace">
        <Link
          className="back-link"
          href={`/workspace/${query}?exchange=${exchange ?? ""}`}
        >
          <ArrowLeft size={16} />
          Back to analysis
        </Link>
        <span className="eyebrow">Historical narrative change</span>
        <h1>
          {instrument
            ? `${instrument.symbol} Market Shift`
            : "Market Shift history"}
        </h1>
        {error && (
          <div className="state-panel error" role="alert">
            {error}
          </div>
        )}
        {!error && !history && (
          <div className="state-panel">
            <RefreshCw className="spin" />
            Loading history
          </div>
        )}
        {history &&
          (history.items.length ? (
            <div className="history-list">
              {history.items.map((item) => (
                <article key={item.snapshot.calculation_id}>
                  <header>
                    <time>
                      {new Date(item.snapshot.generated_at).toLocaleString()}
                    </time>
                    <span
                      className={`direction-chip ${item.snapshot.direction}`}
                    >
                      {item.snapshot.direction}
                    </span>
                  </header>
                  <div className="history-score">
                    <strong>{item.snapshot.score}</strong>
                    <span>
                      {item.score_change == null
                        ? "First observation"
                        : `${Number(item.score_change) >= 0 ? "+" : ""}${item.score_change} since prior`}
                    </span>
                  </div>
                  <p>
                    Confidence {item.snapshot.confidence}
                    {item.direction_changed ? " · Direction changed" : ""}
                  </p>
                  {item.new_narratives.length > 0 && (
                    <small>New: {item.new_narratives.join(", ")}</small>
                  )}
                  {item.retired_narratives.length > 0 && (
                    <small>Retired: {item.retired_narratives.join(", ")}</small>
                  )}
                </article>
              ))}
            </div>
          ) : (
            <div className="state-panel">
              No successful Market Shift calculations are stored yet.
            </div>
          ))}
      </section>
    </main>
  );
}
