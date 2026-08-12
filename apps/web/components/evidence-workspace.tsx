"use client";

import { ArrowLeft, ExternalLink } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import type {
  InstrumentRef,
  ResearchReportOutput,
} from "@tradesentinel/contracts";
import { loadResearch, resolveInstrument } from "@/lib/workspace-api";
import { WorkspaceNav } from "./workspace-nav";

export function EvidenceWorkspace({
  query,
  exchange,
}: {
  query: string;
  exchange?: string;
}) {
  const [instrument, setInstrument] = useState<InstrumentRef | null>(null);
  const [report, setReport] = useState<ResearchReportOutput | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void resolveInstrument(query, exchange)
      .then((resolved) => {
        if (!resolved.match)
          throw new Error("The instrument is not resolved unambiguously.");
        setInstrument(resolved.match.instrument);
        return loadResearch(resolved.match.instrument);
      })
      .then(setReport)
      .catch((cause: unknown) =>
        setError(cause instanceof Error ? cause.message : "Evidence failed."),
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
          <ArrowLeft size={16} /> Back to analysis
        </Link>
        <span className="eyebrow">Evidence index</span>
        <h1>
          {instrument ? `${instrument.symbol} sources and claims` : "Evidence"}
        </h1>
        {error && (
          <div className="state-panel error" role="alert">
            {error}
          </div>
        )}
        {!error && !report && (
          <div className="state-panel">Loading validated evidence…</div>
        )}
        {report && (
          <div className="evidence-layout">
            <section className="analysis-card">
              <h2>Claims</h2>
              {report.events
                .flatMap((event) => event.claims)
                .map((claim) => (
                  <article className="evidence-claim" key={claim.claim_id}>
                    <span>
                      {claim.confidence_basis} · {claim.confidence}
                    </span>
                    <p>{claim.text}</p>
                    <small>
                      {claim.provider} ·{" "}
                      {new Date(claim.timestamp).toLocaleString()}
                    </small>
                    <code>{claim.extraction_version}</code>
                  </article>
                ))}
            </section>
            <section className="analysis-card">
              <h2>Sources</h2>
              <ul className="source-list">
                {report.sources.map((source) => (
                  <li key={source.source_id}>
                    <a
                      href={source.url}
                      target="_blank"
                      rel="noreferrer noopener"
                    >
                      {source.title} <ExternalLink size={13} />
                    </a>
                    <small>
                      {source.provider} ·{" "}
                      {new Date(source.timestamp).toLocaleString()} ·{" "}
                      {source.timestamp_basis}
                    </small>
                  </li>
                ))}
              </ul>
            </section>
          </div>
        )}
      </section>
    </main>
  );
}
