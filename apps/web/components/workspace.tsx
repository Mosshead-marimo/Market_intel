"use client";

import {
  Activity,
  AlertTriangle,
  BookOpen,
  Building2,
  Gauge,
  LineChart,
  Newspaper,
  RefreshCw,
  Users,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import type {
  FundamentalSnapshot,
  InstrumentRef,
  MarketShiftSnapshot,
  PublicSentimentAnalysis,
  RenderedResponse,
  ResearchReportOutput,
  TechnicalSnapshot,
} from "@tradesentinel/contracts";
import {
  loadFundamentals,
  loadMarket,
  loadMarketShift,
  loadOverview,
  loadResearch,
  loadSentiment,
  loadTechnical,
  resolveInstrument,
  type MarketBundle,
} from "@/lib/workspace-api";
import { InstrumentSearch } from "./instrument-search";
import { ResponseComponentView } from "./response-component";
import { WorkspaceNav } from "./workspace-nav";

type Tab =
  | "overview"
  | "market"
  | "research"
  | "sentiment"
  | "technical"
  | "fundamentals"
  | "market-shift";
type Analysis =
  | RenderedResponse
  | MarketBundle
  | ResearchReportOutput
  | PublicSentimentAnalysis
  | TechnicalSnapshot
  | FundamentalSnapshot
  | MarketShiftSnapshot;

const tabs: { id: Tab; label: string; icon: typeof Activity }[] = [
  { id: "overview", label: "Overview", icon: Gauge },
  { id: "market", label: "Market", icon: LineChart },
  { id: "research", label: "Research", icon: Newspaper },
  { id: "sentiment", label: "Sentiment", icon: Users },
  { id: "technical", label: "Technical", icon: Activity },
  { id: "fundamentals", label: "Fundamentals", icon: Building2 },
  { id: "market-shift", label: "Market Shift", icon: RefreshCw },
];

export function WorkspaceHome() {
  return (
    <main className="workspace-shell">
      <WorkspaceNav current="workspace" />
      <section className="workspace-home">
        <span className="eyebrow">Analysis workspace</span>
        <h1>Evidence, calculations, and narrative change in one place.</h1>
        <p>
          Resolve a canonical listing before analysis. Exchange ambiguity is
          always shown and missing providers remain explicit.
        </p>
        <InstrumentSearch />
        <div className="workspace-principles">
          <article>
            <Gauge />
            <strong>Deterministic metrics</strong>
            <span>
              Indicators and financial calculations never come from an LLM.
            </span>
          </article>
          <article>
            <BookOpen />
            <strong>Traceable evidence</strong>
            <span>
              Research claims preserve provider, source, and timestamp metadata.
            </span>
          </article>
          <article>
            <RefreshCw />
            <strong>Narrative shift</strong>
            <span>
              Market Shift measures observed opinion change—not future prices.
            </span>
          </article>
        </div>
      </section>
    </main>
  );
}

export function InstrumentWorkspace({
  query,
  exchange,
}: {
  query: string;
  exchange?: string;
}) {
  const [instrument, setInstrument] = useState<InstrumentRef | null>(null);
  const [candidates, setCandidates] = useState<InstrumentRef[]>([]);
  const [tab, setTab] = useState<Tab>("overview");
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void resolveInstrument(query, exchange)
      .then((result) => {
        if (result.status === "resolved" && result.match)
          setInstrument(result.match.instrument);
        else setCandidates(result.candidates.map((item) => item.instrument));
      })
      .catch((cause: unknown) =>
        setError(cause instanceof Error ? cause.message : "Resolution failed."),
      )
      .finally(() => setLoading(false));
  }, [query, exchange]);

  const loader = useMemo(() => {
    if (!instrument) return null;
    return {
      overview: () => loadOverview(instrument),
      market: () => loadMarket(instrument),
      research: () => loadResearch(instrument),
      sentiment: () => loadSentiment(instrument),
      technical: () => loadTechnical(instrument),
      fundamentals: () => loadFundamentals(instrument),
      "market-shift": () => loadMarketShift(instrument),
    } satisfies Record<Tab, () => Promise<Analysis>>;
  }, [instrument]);

  const load = useCallback(async () => {
    if (!loader) return;
    setLoading(true);
    setError(null);
    setAnalysis(null);
    try {
      setAnalysis(await loader[tab]());
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Analysis could not be loaded.",
      );
    } finally {
      setLoading(false);
    }
  }, [loader, tab]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <main className="workspace-shell">
      <WorkspaceNav current="workspace" />
      <section className="instrument-workspace">
        <header className="instrument-header">
          <div>
            <InstrumentSearch compact />
            {instrument && (
              <>
                <span className="eyebrow">
                  {instrument.exchange} · {instrument.asset_type}
                </span>
                <h1>
                  {instrument.symbol} <small>{instrument.name}</small>
                </h1>
              </>
            )}
          </div>
          {instrument && (
            <span className="currency-chip">{instrument.currency}</span>
          )}
        </header>
        {candidates.length > 0 && (
          <section className="ambiguity-panel" role="alert">
            <AlertTriangle />
            <div>
              <h2>Choose an exchange</h2>
              <p>This name resolves to multiple canonical listings.</p>
              {candidates.map((item) => (
                <Link
                  key={item.instrument_id}
                  href={`/workspace/${item.symbol}?exchange=${item.exchange}`}
                >
                  {item.symbol} · {item.exchange}
                </Link>
              ))}
            </div>
          </section>
        )}
        {instrument && (
          <>
            <nav className="analysis-tabs" aria-label="Instrument analysis">
              {tabs.map((item) => {
                const Icon = item.icon;
                return (
                  <button
                    key={item.id}
                    aria-current={tab === item.id ? "page" : undefined}
                    onClick={() => setTab(item.id)}
                  >
                    <Icon size={16} />
                    {item.label}
                  </button>
                );
              })}
            </nav>
            <section className="analysis-content" aria-live="polite">
              {loading && <LoadingPanel />}
              {error && (
                <UnavailablePanel message={error} retry={() => void load()} />
              )}
              {!loading && !error && analysis && (
                <AnalysisView
                  tab={tab}
                  value={analysis}
                  instrument={instrument}
                />
              )}
            </section>
          </>
        )}
      </section>
    </main>
  );
}

function LoadingPanel() {
  return (
    <div className="state-panel">
      <span className="spinner" />
      <strong>Loading validated analysis</strong>
      <p>Providers and deterministic capabilities are running.</p>
    </div>
  );
}
function UnavailablePanel({
  message,
  retry,
}: {
  message: string;
  retry: () => void;
}) {
  return (
    <div className="state-panel error" role="alert">
      <AlertTriangle />
      <strong>Analysis unavailable</strong>
      <p>{message}</p>
      <button onClick={retry}>
        <RefreshCw size={15} /> Retry
      </button>
    </div>
  );
}

function AnalysisView({
  tab,
  value,
  instrument,
}: {
  tab: Tab;
  value: Analysis;
  instrument: InstrumentRef;
}) {
  if (tab === "overview") {
    const response = value as RenderedResponse;
    return (
      <div className="component-stack">
        {response.components.map((component) => (
          <ResponseComponentView
            key={component.id}
            value={component}
            evidence={response.evidence}
          />
        ))}
      </div>
    );
  }
  if (tab === "market") return <MarketView value={value as MarketBundle} />;
  if (tab === "research")
    return (
      <ResearchView
        value={value as ResearchReportOutput}
        instrument={instrument}
      />
    );
  if (tab === "sentiment")
    return <SentimentView value={value as PublicSentimentAnalysis} />;
  if (tab === "technical")
    return <TechnicalView value={value as TechnicalSnapshot} />;
  if (tab === "fundamentals")
    return <FundamentalsView value={value as FundamentalSnapshot} />;
  return <MarketShiftView value={value as MarketShiftSnapshot} />;
}

function MarketView({ value }: { value: MarketBundle }) {
  const points = value.history.bars.map((bar) => ({
    timestamp: bar.timestamp,
    value: Number(bar.adjusted_close),
  }));
  return (
    <>
      <MetricCards
        items={[
          ["Last price", `${value.quote.currency} ${value.quote.price}`],
          ["Change", value.quote.change_percent ?? "Unavailable"],
          ["1Y return", value.performance.metrics.total_return],
          ["Volatility", value.performance.metrics.annualized_volatility],
          ["Max drawdown", value.performance.metrics.maximum_drawdown],
          ["Cache", value.quote.cache.disposition],
        ]}
      />
      <SimpleChart title="Adjusted close" points={points} />
      <section className="analysis-card">
        <h2>Corporate actions</h2>
        {value.actions.actions.length ? (
          <ul className="timeline-list">
            {value.actions.actions.map((item) => (
              <li key={`${item.effective_at}-${item.action_type}`}>
                <time>{new Date(item.effective_at).toLocaleDateString()}</time>
                <strong>{item.action_type.replaceAll("_", " ")}</strong>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState label="No corporate actions in this range." />
        )}
      </section>
    </>
  );
}

function ResearchView({
  value,
  instrument,
}: {
  value: ResearchReportOutput;
  instrument: InstrumentRef;
}) {
  return (
    <>
      <MetricCards
        items={[
          ["Sources", String(value.coverage.source_count)],
          ["Events", String(value.coverage.event_count)],
          ["Claims", String(value.coverage.claim_count)],
          ["Duplicates removed", String(value.coverage.duplicate_count)],
        ]}
      />
      <section className="analysis-card">
        <h2>Structured event timeline</h2>
        {value.events.length ? (
          <ul className="timeline-list">
            {value.events.map((event) => (
              <li key={event.event_id}>
                <time>{new Date(event.observed_at).toLocaleDateString()}</time>
                <div>
                  <span className="topic-chip">
                    {event.event_type.replaceAll("_", " ")}
                  </span>
                  <strong>{event.headline}</strong>
                  <small>
                    {event.claims.length} evidence-backed claim
                    {event.claims.length === 1 ? "" : "s"}
                  </small>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState label="No deterministic event rules matched the available sources." />
        )}
        <Link
          className="text-link"
          href={`/workspace/${instrument.symbol}/evidence?exchange=${instrument.exchange}`}
        >
          Inspect sources and claims →
        </Link>
      </section>
    </>
  );
}

function SentimentView({ value }: { value: PublicSentimentAnalysis }) {
  const current = value.snapshot.current;
  return (
    <>
      <MetricCards
        items={[
          ["Mean score", current.mean_score ?? "Unavailable"],
          ["Mentions", String(current.mention_count)],
          ["Confidence", value.snapshot.confidence ?? "Unavailable"],
          ["Shift", value.shift.shift_score ?? "Insufficient"],
          ["Trend", value.trend.direction],
          ["Status", value.snapshot.status],
        ]}
      />
      <SimpleChart
        title="Observed daily sentiment"
        points={value.trend.buckets
          .filter((item) => item.mean_score != null)
          .map((item) => ({
            timestamp: item.day,
            value: Number(item.mean_score),
          }))}
      />
      <section className="analysis-card">
        <h2>Public narratives</h2>
        {value.narratives.narratives.length ? (
          <div className="narrative-grid">
            {value.narratives.narratives.map((item) => (
              <article key={item.narrative_id}>
                <span>{item.method}</span>
                <strong>{item.topic}</strong>
                <small>
                  {item.sentiment} · {item.weighted_share} weighted share
                </small>
              </article>
            ))}
          </div>
        ) : (
          <EmptyState label="No qualifying narratives." />
        )}
      </section>
    </>
  );
}

function TechnicalView({ value }: { value: TechnicalSnapshot }) {
  return (
    <>
      <MetricCards
        items={[
          ["Trend", value.trend?.direction ?? "Unavailable"],
          ["Trend strength", value.trend?.strength ?? "Unavailable"],
          ["Momentum", value.momentum?.direction ?? "Unavailable"],
          ["RSI", value.rsi?.series.latest ?? "Unavailable"],
          ["ADX", value.adx?.latest.adx ?? "Unavailable"],
          ["Volatility regime", value.volatility?.regime ?? "Unavailable"],
        ]}
      />
      {value.rsi && (
        <SimpleChart
          title="RSI"
          points={value.rsi.series.points.map((item) => ({
            timestamp: item.timestamp,
            value: Number(item.value),
          }))}
        />
      )}
      <WarningList values={value.warnings} />
    </>
  );
}

function FundamentalsView({ value }: { value: FundamentalSnapshot }) {
  const sections = [
    value.revenue,
    value.profit,
    value.cash_flow,
    value.debt,
    value.margins,
    value.roe,
    value.roce,
  ];
  return (
    <>
      <MetricCards
        items={[
          ["Status", value.status],
          ["Sector", value.profile.sector ?? "Unavailable"],
          ["Industry", value.profile.industry ?? "Unavailable"],
          ["Currency", value.profile.reporting_currency ?? "Unavailable"],
          [
            "Data cutoff",
            value.data_cutoff
              ? new Date(value.data_cutoff).toLocaleDateString()
              : "Unavailable",
          ],
        ]}
      />
      <div className="fundamental-grid">
        {sections.map((section) => (
          <section className="analysis-card" key={section.section}>
            <h2>{section.section.replaceAll("_", " ")}</h2>
            <span className={`status-chip ${section.status}`}>
              {section.status}
            </span>
            {section.metrics.map((metric) => (
              <div className="metric-row" key={metric.concept}>
                <span>{metric.label}</span>
                <strong>{metric.latest ?? "—"}</strong>
                <small>
                  {metric.annual.length} annual · {metric.quarterly.length}{" "}
                  quarterly
                </small>
              </div>
            ))}
          </section>
        ))}
      </div>
      <WarningList values={value.warnings} />
    </>
  );
}

function MarketShiftView({ value }: { value: MarketShiftSnapshot }) {
  const score = Number(value.score);
  return (
    <>
      <section className="shift-hero">
        <div
          className={`score-orb ${value.direction}`}
          style={{ "--score": `${Math.abs(score)}%` } as React.CSSProperties}
        >
          <strong>{value.score}</strong>
          <span>-100 to 100</span>
        </div>
        <div>
          <span className="eyebrow">Observed narrative change</span>
          <h2>{value.direction}</h2>
          <p>
            Confidence {value.confidence}. This quality score is not a
            prediction probability.
          </p>
          <small>
            {new Date(value.window.previous_start).toLocaleDateString()} →{" "}
            {new Date(value.window.end).toLocaleDateString()}
          </small>
        </div>
      </section>
      <section className="analysis-card">
        <h2>Category contributions</h2>
        <div className="contribution-list">
          {value.category_signals.map((item) => (
            <div key={item.category}>
              <span>{item.category.replaceAll("_", " ")}</span>
              <div>
                <i
                  style={{
                    width: `${Math.min(100, Math.abs(Number(item.score)) * 100)}%`,
                  }}
                  data-negative={Number(item.score) < 0}
                />
              </div>
              <strong>{item.weighted_contribution}</strong>
            </div>
          ))}
        </div>
      </section>
      <div className="driver-columns">
        <DriverList title="Catalysts" values={value.catalysts} />
        <DriverList title="Risks" values={value.risks} />
      </div>
      <section className="analysis-card">
        <h2>Narrative changes</h2>
        {value.narratives.length ? (
          <div className="narrative-grid">
            {value.narratives.map((item) => (
              <article key={item.narrative_id}>
                <span>{item.direction}</span>
                <strong>{item.label}</strong>
                <small>
                  Change {item.change} · {item.evidence_ids.length} evidence
                  link(s)
                </small>
              </article>
            ))}
          </div>
        ) : (
          <EmptyState label="No material narrative changes." />
        )}
        <Link
          className="text-link"
          href={`/workspace/${value.instrument.symbol}/market-shift/history?exchange=${value.instrument.exchange}`}
        >
          View historical changes →
        </Link>
      </section>
    </>
  );
}

function MetricCards({ items }: { items: [string, string][] }) {
  return (
    <section className="workspace-metrics">
      {items.map(([label, value]) => (
        <article key={label}>
          <span>{label}</span>
          <strong>{value}</strong>
        </article>
      ))}
    </section>
  );
}
function SimpleChart({
  title,
  points,
}: {
  title: string;
  points: { timestamp: string; value: number }[];
}) {
  if (!points.length)
    return (
      <section className="analysis-card">
        <h2>{title}</h2>
        <EmptyState label="No chart observations." />
      </section>
    );
  const width = 800,
    height = 240,
    values = points.map((item) => item.value),
    min = Math.min(...values),
    max = Math.max(...values),
    spread = max - min || 1;
  const polyline = points
    .map(
      (item, index) =>
        `${points.length === 1 ? width / 2 : (index / (points.length - 1)) * width},${height - 16 - ((item.value - min) / spread) * (height - 32)}`,
    )
    .join(" ");
  return (
    <figure className="workspace-chart">
      <figcaption>
        <strong>{title}</strong>
        <span>{points.length} observations</span>
      </figcaption>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={`${title}, ${points.length} observations from ${new Date(points[0].timestamp).toLocaleDateString()} to ${new Date(points.at(-1)!.timestamp).toLocaleDateString()}`}
      >
        <line x1="0" y1={height - 16} x2={width} y2={height - 16} />
        <polyline points={polyline} />
      </svg>
    </figure>
  );
}
function DriverList({
  title,
  values,
}: {
  title: string;
  values: MarketShiftSnapshot["catalysts"];
}) {
  return (
    <section className="analysis-card">
      <h2>{title}</h2>
      {values.length ? (
        <ul className="driver-list">
          {values.map((item) => (
            <li key={`${item.category}-${item.label}`}>
              <strong>{item.label}</strong>
              <span>{item.category.replaceAll("_", " ")}</span>
              <small>
                Contribution {item.contribution} · Confidence {item.confidence}
              </small>
            </li>
          ))}
        </ul>
      ) : (
        <EmptyState label={`No material ${title.toLowerCase()}.`} />
      )}
    </section>
  );
}
function WarningList({ values }: { values: string[] }) {
  return values.length ? (
    <aside className="warning-stack">
      {values.map((item) => (
        <p key={item}>
          <AlertTriangle size={15} />
          {item}
        </p>
      ))}
    </aside>
  ) : null;
}
function EmptyState({ label }: { label: string }) {
  return <p className="workspace-empty">{label}</p>;
}
