import {
  responseComponentSchema,
  type ResponseComponent,
} from "@tradesentinel/contracts";

function StateMessage({ component }: { component: ResponseComponent }) {
  if (component.status === "ready") return null;
  return (
    <p className={`component-state ${component.status}`}>
      {component.status.replace("_", " ")}
    </p>
  );
}

export function ResponseComponentView({ value }: { value: unknown }) {
  const parsed = responseComponentSchema.safeParse(value);
  if (!parsed.success)
    return (
      <div className="component-error" role="alert">
        Unsupported response data
      </div>
    );
  const component = parsed.data;
  if (component.type === "summary_card") {
    return (
      <article className="response-card">
        <StateMessage component={component} />
        <p className="eyebrow">System response</p>
        <h3>{component.heading}</h3>
        <p>{component.body}</p>
      </article>
    );
  }
  if (component.type === "metric_grid") {
    return (
      <section
        className="metric-grid"
        aria-label={component.title ?? "Metrics"}
      >
        {component.metrics.map((metric) => (
          <div key={metric.label}>
            <span>{metric.label}</span>
            <strong>{metric.value}</strong>
            {metric.detail && <small>{metric.detail}</small>}
          </div>
        ))}
      </section>
    );
  }
  if (component.type === "warning_banner")
    return (
      <aside className="warning" role="status">
        {component.message}
      </aside>
    );
  if (component.type === "source_list")
    return (
      <section>
        <h3>{component.title ?? "Sources"}</h3>
        <p>
          {component.sources.length
            ? `${component.sources.length} sources`
            : "No sources available."}
        </p>
      </section>
    );
  if (
    component.type === "scenario_table" ||
    component.type === "comparison_table"
  )
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
  return (
    <article className="response-card">
      <StateMessage component={component} />
      <h3>{component.title ?? component.type.replaceAll("_", " ")}</h3>
      <p>Validated component ready for module-provided data.</p>
    </article>
  );
}
