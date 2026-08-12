"use client";

import { ArrowRight, Search } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import type { InstrumentMatch } from "@tradesentinel/contracts";
import { autocompleteInstrument } from "@/lib/workspace-api";

export function InstrumentSearch({ compact = false }: { compact?: boolean }) {
  const [query, setQuery] = useState("");
  const [matches, setMatches] = useState<InstrumentMatch[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (query.trim().length < 2) {
      setMatches([]);
      return;
    }
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      void autocompleteInstrument(query)
        .then((value) => {
          if (!controller.signal.aborted) setMatches(value.matches);
        })
        .catch(() => {
          if (!controller.signal.aborted)
            setError("Instrument search is temporarily unavailable.");
        });
    }, 180);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [query]);

  return (
    <div className={`instrument-search ${compact ? "compact" : ""}`}>
      <label
        htmlFor={compact ? "instrument-search-compact" : "instrument-search"}
      >
        {compact ? "Change instrument" : "Find an instrument"}
      </label>
      <div className="search-input">
        <Search size={18} aria-hidden="true" />
        <input
          id={compact ? "instrument-search-compact" : "instrument-search"}
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setError(null);
          }}
          placeholder="Ticker, company, or alias"
          autoComplete="off"
        />
      </div>
      {error && <p className="inline-error">{error}</p>}
      {matches.length > 0 && (
        <ul className="instrument-results" aria-label="Instrument matches">
          {matches.map(({ instrument, confidence }) => (
            <li key={instrument.instrument_id}>
              <Link
                href={`/workspace/${encodeURIComponent(instrument.symbol)}?exchange=${encodeURIComponent(instrument.exchange)}`}
              >
                <span>
                  <strong>{instrument.symbol}</strong>
                  <small>{instrument.name}</small>
                </span>
                <span className="exchange-chip">{instrument.exchange}</span>
                <span className="match-score">
                  {Math.round(confidence * 100)}%
                </span>
                <ArrowRight size={16} aria-hidden="true" />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
