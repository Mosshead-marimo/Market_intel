import { z } from "zod";

export const componentStatusSchema = z.enum([
  "ready",
  "partial",
  "empty",
  "stale",
  "error",
]);
const componentBase = z.object({
  id: z.string(),
  title: z.string().nullable().optional(),
  status: componentStatusSchema.default("ready"),
  source_ids: z.array(z.string()).default([]),
});

export const summaryCardSchema = componentBase.extend({
  type: z.literal("summary_card"),
  heading: z.string(),
  body: z.string(),
});

export const metricGridSchema = componentBase.extend({
  type: z.literal("metric_grid"),
  metrics: z.array(
    z.object({
      label: z.string(),
      value: z.string(),
      detail: z.string().nullable().optional(),
    }),
  ),
});

const chartSchema = z.object({
  series: z.array(
    z.object({
      name: z.string(),
      points: z.array(z.object({ timestamp: z.string(), value: z.number() })),
    }),
  ),
});
const tableSchema = z.object({
  columns: z.array(z.string()),
  rows: z.array(z.object({ cells: z.array(z.string()) })),
});

export const responseComponentSchema = z.discriminatedUnion("type", [
  summaryCardSchema,
  metricGridSchema,
  componentBase.extend({
    type: z.literal("price_chart"),
    ...chartSchema.shape,
  }),
  componentBase.extend({
    type: z.literal("sentiment_chart"),
    ...chartSchema.shape,
  }),
  componentBase.extend({
    type: z.literal("news_timeline"),
    items: z.array(
      z.object({
        occurred_at: z.string(),
        headline: z.string(),
        description: z.string().nullable().optional(),
        source_id: z.string().nullable().optional(),
      }),
    ),
  }),
  componentBase.extend({
    type: z.literal("prediction_card"),
    direction: z.enum(["rise", "sideways", "decline", "uncertain"]),
    confidence: z.number().min(0).max(1),
    horizon: z.string(),
    generated_at: z.string(),
    data_cutoff: z.string(),
    model_version: z.string(),
  }),
  componentBase.extend({
    type: z.literal("scenario_table"),
    ...tableSchema.shape,
  }),
  componentBase.extend({
    type: z.literal("comparison_table"),
    ...tableSchema.shape,
  }),
  componentBase.extend({
    type: z.literal("risk_card"),
    risks: z.array(
      z.object({
        label: z.string(),
        severity: z.enum(["low", "medium", "high", "unknown"]),
        description: z.string(),
      }),
    ),
  }),
  componentBase.extend({
    type: z.literal("source_list"),
    sources: z.array(z.record(z.unknown())),
  }),
  componentBase.extend({
    type: z.literal("warning_banner"),
    code: z.string(),
    message: z.string(),
  }),
]);

export const capabilityDescriptorSchema = z.object({
  name: z.string(),
  version: z.string(),
  description: z.string(),
  dependencies: z.array(z.string()),
  permissions: z.array(z.string()),
  provides: z.array(z.string()),
});

export const commandDescriptorSchema = z.object({
  name: z.string(),
  description: z.string(),
  target: z.object({
    kind: z.enum(["capability", "workflow"]),
    name: z.string(),
  }),
  arguments: z.array(z.object({ name: z.string(), required: z.boolean() })),
  options: z.array(
    z.object({
      name: z.string(),
      destination: z.string(),
      flag: z.boolean(),
      required: z.boolean(),
    }),
  ),
  examples: z.array(z.string()),
});

export const healthSchema = z.object({
  service: z.string(),
  version: z.string(),
  status: z.enum(["healthy", "degraded", "unhealthy"]),
  checked_at: z.string(),
  dependencies: z.array(
    z.object({
      name: z.string(),
      status: z.enum(["healthy", "unhealthy", "disabled"]),
      latency_ms: z.number().nullable().optional(),
      detail: z.string().nullable().optional(),
    }),
  ),
});

export const capabilityResultSchema = z.object({
  capability: z.string(),
  status: z.enum([
    "pending",
    "running",
    "completed",
    "partial",
    "failed",
    "skipped",
  ]),
  data: z.record(z.unknown()),
  summary: z.string().nullable().optional(),
  sources: z.array(z.record(z.unknown())),
  warnings: z.array(
    z.object({
      code: z.string(),
      message: z.string(),
      retryable: z.boolean(),
      details: z.record(z.unknown()),
    }),
  ),
  components: z.array(responseComponentSchema),
  metadata: z.record(z.unknown()),
});

export const workflowResultSchema = z.object({
  workflow: z.string(),
  run_id: z.string().uuid(),
  status: z.enum([
    "pending",
    "running",
    "completed",
    "partial",
    "failed",
    "skipped",
  ]),
  steps: z.record(capabilityResultSchema),
  warnings: z.array(
    z.object({
      code: z.string(),
      message: z.string(),
      retryable: z.boolean(),
      details: z.record(z.unknown()),
    }),
  ),
  started_at: z.string(),
  completed_at: z.string(),
});

export const renderedResponseSchema = z.object({
  status: z.enum([
    "pending",
    "running",
    "completed",
    "partial",
    "failed",
    "skipped",
  ]),
  text: z.string(),
  components: z.array(responseComponentSchema),
  sources: z.array(z.record(z.unknown())),
  warnings: z.array(
    z.object({
      code: z.string(),
      message: z.string(),
      retryable: z.boolean(),
      details: z.record(z.unknown()),
    }),
  ),
  run_id: z.string().uuid().nullable().optional(),
  generated_at: z.string(),
  trace: z.array(z.string()),
});

export const commandResponseSchema = z.object({
  request_id: z.string().uuid(),
  result: z.union([capabilityResultSchema, workflowResultSchema]),
  response: renderedResponseSchema,
});

export type ResponseComponent = z.infer<typeof responseComponentSchema>;
export type CapabilityDescriptor = z.infer<typeof capabilityDescriptorSchema>;
export type CommandDescriptor = z.infer<typeof commandDescriptorSchema>;
export type Health = z.infer<typeof healthSchema>;
export type CommandResponse = z.infer<typeof commandResponseSchema>;
