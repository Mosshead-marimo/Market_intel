"use client";

import type { ModelPerformanceReport } from "@tradesentinel/contracts";
import { RefreshCw, RotateCcw } from "lucide-react";
import { useState } from "react";
import {
  loadModelPerformance,
  rebuildModelPerformance,
  type PerformanceQuery,
} from "../lib/workspace-api";
import { TokenGate } from "./token-gate";
import { WorkspaceNav } from "./workspace-nav";

function percent(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `${(Number(value) * 100).toFixed(1)}%`;
}

function PerformancePanel({ token }: { token: string }) {
  const [report, setReport] = useState<ModelPerformanceReport | null>(null);
  const [filters, setFilters] = useState<PerformanceQuery>({});
  const [status, setStatus] = useState(
    "Load metrics to inspect evaluated predictions.",
  );

  const load = () => {
    setStatus("Loading validated performance metrics…");
    void loadModelPerformance(token, filters)
      .then((value) => {
        setReport(value);
        setStatus(
          `${value.overall.sample_count} evaluated predictions loaded.`,
        );
      })
      .catch((cause: unknown) =>
        setStatus(
          cause instanceof Error
            ? cause.message
            : "Performance request failed.",
        ),
      );
  };

  return (
    <section className="admin-workspace performance-workspace">
      <header>
        <div>
          <span className="eyebrow">Internal model monitoring</span>
          <h1>Model performance</h1>
          <p>
            Observed accuracy and calibration only. This surface does not
            publish forecasts.
          </p>
        </div>
        <div className="admin-toolbar">
          <button onClick={load}>
            <RefreshCw size={16} />
            Load
          </button>
          <button
            onClick={() => void rebuildModelPerformance(token).then(load)}
          >
            <RotateCcw size={16} />
            Rebuild aggregates
          </button>
        </div>
      </header>

      <div className="performance-filters" aria-label="Performance filters">
        <label>
          Model
          <input
            value={filters.modelVersion ?? ""}
            onChange={(event) =>
              setFilters({
                ...filters,
                modelVersion: event.target.value || undefined,
              })
            }
          />
        </label>
        <label>
          Horizon
          <select
            value={filters.horizon ?? ""}
            onChange={(event) =>
              setFilters({
                ...filters,
                horizon: event.target.value
                  ? (Number(event.target.value) as 5 | 20)
                  : undefined,
              })
            }
          >
            <option value="">All</option>
            <option value="5">5 sessions</option>
            <option value="20">20 sessions</option>
          </select>
        </label>
        <label>
          Asset type
          <input
            value={filters.assetType ?? ""}
            onChange={(event) =>
              setFilters({
                ...filters,
                assetType: event.target.value || undefined,
              })
            }
          />
        </label>
        <label>
          Exchange
          <input
            value={filters.exchange ?? ""}
            onChange={(event) =>
              setFilters({
                ...filters,
                exchange: event.target.value || undefined,
              })
            }
          />
        </label>
        <label>
          Sector
          <input
            value={filters.sector ?? ""}
            onChange={(event) =>
              setFilters({
                ...filters,
                sector: event.target.value || undefined,
              })
            }
          />
        </label>
        <label>
          Evaluated after
          <input
            type="date"
            value={filters.start ?? ""}
            onChange={(event) =>
              setFilters({ ...filters, start: event.target.value || undefined })
            }
          />
        </label>
        <label>
          Evaluated before
          <input
            type="date"
            value={filters.end ?? ""}
            onChange={(event) =>
              setFilters({ ...filters, end: event.target.value || undefined })
            }
          />
        </label>
      </div>
      <p className="admin-message" role="status">
        {status}
      </p>

      {report && (
        <>
          <div className="performance-metrics">
            <article>
              <span>Evaluated</span>
              <strong>{report.overall.sample_count}</strong>
            </article>
            <article>
              <span>Directional coverage</span>
              <strong>{percent(report.overall.directional_coverage)}</strong>
            </article>
            <article>
              <span>Directional accuracy</span>
              <strong>{percent(report.overall.directional_accuracy)}</strong>
            </article>
            <article>
              <span>Calibration error</span>
              <strong>
                {percent(report.overall.expected_calibration_error)}
              </strong>
            </article>
            <article>
              <span>Return range accuracy</span>
              <strong>{percent(report.overall.return_range_accuracy)}</strong>
            </article>
            <article>
              <span>Price range accuracy</span>
              <strong>{percent(report.overall.price_range_accuracy)}</strong>
            </article>
          </div>

          <div className="admin-columns">
            <section className="analysis-card">
              <h2>Evaluation queue</h2>
              <dl className="queue-counts">
                <div>
                  <dt>Scheduled</dt>
                  <dd>{report.scheduled}</dd>
                </div>
                <div>
                  <dt>Waiting</dt>
                  <dd>{report.waiting}</dd>
                </div>
                <div>
                  <dt>Retrying</dt>
                  <dd>{report.retrying}</dd>
                </div>
                <div>
                  <dt>Overdue</dt>
                  <dd>{report.overdue}</dd>
                </div>
              </dl>
            </section>
            <section className="analysis-card">
              <h2>Confusion matrix</h2>
              <div className="table-scroll">
                <table>
                  <caption>Predicted rows and realized columns</caption>
                  <thead>
                    <tr>
                      <th>Predicted</th>
                      {report.confusion_matrix.actual_labels.map((label) => (
                        <th key={label}>{label}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {report.confusion_matrix.predicted_labels.map(
                      (label, row) => (
                        <tr key={label}>
                          <th>{label}</th>
                          {report.confusion_matrix.counts[row]?.map(
                            (count, column) => (
                              <td key={`${row}-${column}`}>{count}</td>
                            ),
                          )}
                        </tr>
                      ),
                    )}
                  </tbody>
                </table>
              </div>
            </section>
          </div>

          <section className="analysis-card">
            <h2>Calibration reliability</h2>
            <p className="chart-summary">
              Ten probability bins per class. Bar width compares observed
              frequency with mean predicted probability.
            </p>
            <div className="calibration-grid">
              {report.calibration
                .filter((bin) => bin.samples > 0)
                .map((bin) => (
                  <div key={`${bin.class_name}-${bin.lower_bound}`}>
                    <span>
                      {bin.class_name} · {Number(bin.lower_bound).toFixed(1)}–
                      {Number(bin.upper_bound).toFixed(1)} ({bin.samples})
                    </span>
                    <div className="calibration-track">
                      <i style={{ width: percent(bin.mean_probability) }} />
                      <b style={{ width: percent(bin.observed_frequency) }} />
                    </div>
                  </div>
                ))}
            </div>
          </section>

          <section className="analysis-card">
            <h2>Rolling and cohort performance</h2>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Dimension</th>
                    <th>Cohort</th>
                    <th>Samples</th>
                    <th>Coverage</th>
                    <th>Accuracy</th>
                    <th>Brier</th>
                    <th>Range</th>
                  </tr>
                </thead>
                <tbody>
                  {report.cohorts.map((cohort) => (
                    <tr key={`${cohort.dimension}-${cohort.key}`}>
                      <td>{cohort.dimension}</td>
                      <th>{cohort.key}</th>
                      <td>{cohort.metrics.sample_count}</td>
                      <td>{percent(cohort.metrics.directional_coverage)}</td>
                      <td>{percent(cohort.metrics.directional_accuracy)}</td>
                      <td>
                        {cohort.metrics.multiclass_brier === null
                          ? "—"
                          : Number(cohort.metrics.multiclass_brier).toFixed(3)}
                      </td>
                      <td>{percent(cohort.metrics.price_range_accuracy)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </section>
  );
}

export function ModelPerformanceWorkspace() {
  return (
    <main className="workspace-shell">
      <WorkspaceNav current="admin" />
      <TokenGate title="Model performance">
        {(token) => <PerformancePanel token={token} />}
      </TokenGate>
    </main>
  );
}
