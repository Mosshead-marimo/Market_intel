import {
  responseComponentSchema,
  type EvidenceRecord,
  type ResponseComponent,
} from "@tradesentinel/contracts";

type ComponentProps = {
  evidence?: EvidenceRecord[];
  onFollowUp?: (prompt: string) => void;
};

function GroundedClaimView({
  claim,
  evidence,
}: {
  claim: ComponentOf<"cited_narrative">["claims"][number];
  evidence: EvidenceRecord[];
}) {
  return (
    <>
      {claim.text}{" "}
      <span className="citation-list" aria-label="Evidence citations">
        {claim.evidence_ids.map((id) => {
          const record = evidence.find((item) => item.evidence_id === id);
          return (
            <abbr
              key={id}
              className="citation-badge"
              title={record ? `${record.title}: ${record.value}` : id}
            >
              {record?.provider ?? id.slice(-4)}
            </abbr>
          );
        })}
      </span>
    </>
  );
}

type ComponentOf<Type extends ResponseComponent["type"]> = Extract<
  ResponseComponent,
  { type: Type }
>;

function StateMessage({ component }: { component: ResponseComponent }) {
  if (component.status === "ready") return null;
  return (
    <p className={`component-state ${component.status}`}>
      {component.status.replace("_", " ")}
    </p>
  );
}

function MetricGridView({
  component,
}: {
  component: ComponentOf<"metric_grid">;
}) {
  return (
    <section className="metric-grid" aria-label={component.title ?? "Metrics"}>
      {component.metrics.map((metric) => (
        <div key={`${metric.label}-${metric.value}`}>
          <span>{metric.label}</span>
          <strong>{metric.value}</strong>
          {metric.detail && <small>{metric.detail}</small>}
        </div>
      ))}
    </section>
  );
}

function LineChartView({
  component,
}: {
  component: ComponentOf<"price_chart"> | ComponentOf<"sentiment_chart">;
}) {
  const points = component.series.flatMap((series) => series.points);
  if (!points.length)
    return <p className="component-empty">No chart observations available.</p>;
  const values = points.map((point) => point.value);
  const minimum = Math.min(...values);
  const maximum = Math.max(...values);
  const spread = maximum - minimum || 1;
  const width = 640;
  const height = 190;
  return (
    <figure className="line-chart">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={component.title ?? "Time series chart"}
      >
        {component.series.map((series, seriesIndex) => {
          const path = series.points
            .map((point, index) => {
              const x =
                series.points.length === 1
                  ? width / 2
                  : (index / (series.points.length - 1)) * width;
              const y =
                height - ((point.value - minimum) / spread) * (height - 16) - 8;
              return `${x.toFixed(2)},${y.toFixed(2)}`;
            })
            .join(" ");
          return (
            <polyline
              key={series.name}
              points={path}
              className={`chart-series chart-series-${seriesIndex % 4}`}
            />
          );
        })}
      </svg>
      <figcaption>
        {component.series.map((series) => series.name).join(" · ")}
      </figcaption>
    </figure>
  );
}

function TimelineView({
  component,
}: {
  component: ComponentOf<"news_timeline"> | ComponentOf<"event_timeline">;
}) {
  return (
    <ol className="event-timeline" aria-label={component.title ?? "Timeline"}>
      {component.items.map((item, index) => {
        const label = "headline" in item ? item.headline : item.label;
        return (
          <li key={`${item.occurred_at}-${label}-${index}`}>
            <time dateTime={item.occurred_at}>
              {new Date(item.occurred_at).toLocaleDateString()}
            </time>
            <strong>{label}</strong>
            {item.description && <p>{item.description}</p>}
          </li>
        );
      })}
    </ol>
  );
}

function TableView({
  component,
}: {
  component: ComponentOf<"scenario_table"> | ComponentOf<"comparison_table">;
}) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {component.columns.map((column) => (
              <th key={column}>{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {component.rows.map((row, index) => (
            <tr key={index}>
              {row.cells.map((cell, cellIndex) => (
                <td key={cellIndex}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SourceListView({
  component,
}: {
  component: ComponentOf<"source_list">;
}) {
  return (
    <ul className="source-list">
      {component.sources.map((source, index) => {
        const title =
          typeof source.title === "string"
            ? source.title
            : `Source ${index + 1}`;
        const url = typeof source.url === "string" ? source.url : null;
        return (
          <li
            key={
              typeof source.source_id === "string" ? source.source_id : index
            }
          >
            {url ? (
              <a href={url} target="_blank" rel="noreferrer noopener">
                {title}
              </a>
            ) : (
              title
            )}
          </li>
        );
      })}
    </ul>
  );
}

function LeafComponentView({
  component,
  evidence = [],
  onFollowUp,
}: {
  component: Exclude<ResponseComponent, ComponentOf<"response_section">>;
} & ComponentProps) {
  if (component.type === "summary_card")
    return (
      <article className="response-card">
        <StateMessage component={component} />
        <p className="eyebrow">System response</p>
        <h3>{component.heading}</h3>
        <p>{component.body}</p>
      </article>
    );
  if (component.type === "metric_grid")
    return <MetricGridView component={component} />;
  if (component.type === "price_chart" || component.type === "sentiment_chart")
    return <LineChartView component={component} />;
  if (component.type === "news_timeline" || component.type === "event_timeline")
    return <TimelineView component={component} />;
  if (
    component.type === "scenario_table" ||
    component.type === "comparison_table"
  )
    return <TableView component={component} />;
  if (component.type === "warning_banner")
    return (
      <aside className="warning" role="status">
        {component.message}
      </aside>
    );
  if (component.type === "source_list")
    return <SourceListView component={component} />;
  if (component.type === "cited_narrative")
    return (
      <section
        className="cited-narrative"
        aria-label={component.title ?? "Evidence-grounded response"}
      >
        {component.claims.map((claim) => (
          <p key={claim.claim_id}>
            <GroundedClaimView claim={claim} evidence={evidence} />
          </p>
        ))}
      </section>
    );
  if (component.type === "market_thesis")
    return (
      <section
        className="market-thesis"
        aria-label={component.title ?? "Balanced market thesis"}
      >
        {(
          [
            ["Supportive evidence", component.supportive],
            ["Contradictory evidence", component.contradictory],
            ["Uncertainties", component.uncertainties],
          ] as const
        ).map(([heading, claims]) => (
          <div key={heading}>
            <h4>{heading}</h4>
            {claims.length ? (
              <ul>
                {claims.map((claim) => (
                  <li key={claim.claim_id}>
                    <GroundedClaimView claim={claim} evidence={evidence} />
                  </li>
                ))}
              </ul>
            ) : (
              <p>No supported claims available.</p>
            )}
          </div>
        ))}
      </section>
    );
  if (component.type === "follow_up_questions")
    return (
      <div
        className="follow-up-questions"
        aria-label={component.title ?? "Follow-up questions"}
      >
        {component.questions.map((question) => (
          <button
            key={question.id}
            type="button"
            onClick={() => onFollowUp?.(question.prompt)}
          >
            {question.label}
          </button>
        ))}
      </div>
    );
  if (component.type === "risk_card")
    return (
      <ul className="risk-list">
        {component.risks.map((risk) => (
          <li key={risk.label} data-severity={risk.severity}>
            <strong>{risk.label}</strong> {risk.description}
          </li>
        ))}
      </ul>
    );
  return (
    <article className="response-card">
      <StateMessage component={component} />
      <h3>{component.title ?? "Prediction context"}</h3>
      <p>
        {component.direction} · {component.confidence}
      </p>
      <small>{component.horizon}</small>
    </article>
  );
}

function ValidatedComponentView({
  component,
  evidence,
  onFollowUp,
}: {
  component: ResponseComponent;
} & ComponentProps) {
  if (component.type === "response_section")
    return (
      <section
        className="response-section"
        aria-labelledby={`${component.id}-title`}
      >
        <header>
          <div>
            <h3 id={`${component.id}-title`}>
              {component.title ?? component.id}
            </h3>
            {component.description && <p>{component.description}</p>}
          </div>
          <StateMessage component={component} />
        </header>
        <div className="response-section-content">
          {component.items.map((item) => (
            <LeafComponentView
              key={item.id}
              component={item}
              evidence={evidence}
              onFollowUp={onFollowUp}
            />
          ))}
        </div>
      </section>
    );
  return (
    <LeafComponentView
      component={component}
      evidence={evidence}
      onFollowUp={onFollowUp}
    />
  );
}

export function ResponseComponentView({
  value,
  evidence,
  onFollowUp,
}: { value: unknown } & ComponentProps) {
  const parsed = responseComponentSchema.safeParse(value);
  if (!parsed.success)
    return (
      <div className="component-error" role="alert">
        Unsupported response data
      </div>
    );
  return (
    <ValidatedComponentView
      component={parsed.data}
      evidence={evidence}
      onFollowUp={onFollowUp}
    />
  );
}
