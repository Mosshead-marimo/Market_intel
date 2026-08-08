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

export const apiErrorDetailSchema = z.object({
  code: z.string(),
  message: z.string(),
  retryable: z.boolean(),
  details: z.record(z.unknown()),
});

export const chatSessionStatusSchema = z.enum(["active", "archived"]);
export const chatTurnStatusSchema = z.enum([
  "queued",
  "planning",
  "executing",
  "rendering",
  "completed",
  "partial",
  "failed",
]);
export const chatMessageStatusSchema = z.enum([
  "accepted",
  "streaming",
  "completed",
  "partial",
  "failed",
]);

export const chatSessionSchema = z.object({
  id: z.string().uuid(),
  title: z.string(),
  status: chatSessionStatusSchema,
  created_at: z.string(),
  updated_at: z.string(),
  archived_at: z.string().nullable().optional(),
});

export const chatMessageSchema = z.object({
  id: z.string().uuid(),
  session_id: z.string().uuid(),
  turn_id: z.string().uuid(),
  role: z.enum(["user", "assistant"]),
  content: z.string(),
  status: chatMessageStatusSchema,
  response: renderedResponseSchema.nullable().optional(),
  error: apiErrorDetailSchema.nullable().optional(),
  created_at: z.string(),
  completed_at: z.string().nullable().optional(),
});

export const chatTurnSchema = z.object({
  id: z.string().uuid(),
  session_id: z.string().uuid(),
  client_message_id: z.string().uuid(),
  user_message_id: z.string().uuid(),
  assistant_message_id: z.string().uuid().nullable().optional(),
  status: chatTurnStatusSchema,
  request_id: z.string().uuid(),
  correlation_id: z.string().uuid(),
  run_id: z.string().uuid().nullable().optional(),
  attempt: z.number().int().nonnegative(),
  lease_expires_at: z.string().nullable().optional(),
  error: apiErrorDetailSchema.nullable().optional(),
  created_at: z.string(),
  started_at: z.string().nullable().optional(),
  completed_at: z.string().nullable().optional(),
});

export const chatSessionDetailSchema = z.object({
  session: chatSessionSchema,
  messages: z.array(chatMessageSchema),
  active_turn: chatTurnSchema.nullable().optional(),
});

export const chatSessionPageSchema = z.object({
  items: z.array(chatSessionSchema),
  next_cursor: z.string().nullable().optional(),
});

export const chatTurnAcceptedSchema = z.object({
  session_id: z.string().uuid(),
  turn_id: z.string().uuid(),
  user_message_id: z.string().uuid(),
  status: chatTurnStatusSchema,
  stream_url: z.string(),
});

const chatStreamBaseSchema = z.object({
  version: z.string(),
  event_id: z.string().uuid(),
  sequence: z.number().int().positive(),
  occurred_at: z.string(),
  session_id: z.string().uuid(),
  turn_id: z.string().uuid(),
  request_id: z.string().uuid(),
  correlation_id: z.string().uuid(),
  run_id: z.string().uuid().nullable().optional(),
});

export const chatStreamEventSchema = z.discriminatedUnion("type", [
  chatStreamBaseSchema.extend({
    type: z.literal("status"),
    status: chatTurnStatusSchema,
    message: z.string(),
  }),
  chatStreamBaseSchema.extend({
    type: z.literal("typing"),
    active: z.boolean(),
  }),
  chatStreamBaseSchema.extend({
    type: z.literal("progress"),
    stage: z.string(),
    label: z.string(),
    current: z.number().int().nonnegative().nullable().optional(),
    total: z.number().int().nonnegative().nullable().optional(),
  }),
  chatStreamBaseSchema.extend({
    type: z.literal("response"),
    delta: z.string(),
  }),
  chatStreamBaseSchema.extend({
    type: z.literal("component"),
    component: responseComponentSchema,
  }),
  chatStreamBaseSchema.extend({
    type: z.literal("warning"),
    warning: capabilityResultSchema.shape.warnings.element,
  }),
  chatStreamBaseSchema.extend({
    type: z.literal("complete"),
    turn: chatTurnSchema,
    message: chatMessageSchema,
  }),
  chatStreamBaseSchema.extend({
    type: z.literal("error"),
    error: apiErrorDetailSchema,
  }),
]);

export const assetTypeSchema = z.enum([
  "equity",
  "etf",
  "index",
  "fund",
  "currency",
  "commodity",
  "crypto",
  "other",
]);

export const instrumentRefSchema = z.object({
  instrument_id: z.string().uuid(),
  symbol: z.string().min(1),
  name: z.string().min(1),
  exchange: z.string().min(1),
  asset_type: assetTypeSchema,
  currency: z.string().min(1),
  aliases: z.array(z.string()),
});

export const instrumentMatchSchema = z.object({
  instrument: instrumentRefSchema,
  confidence: z.number().min(0).max(1),
  matched_on: z.enum(["ticker", "name", "alias"]),
  matched_value: z.string(),
});

export const instrumentSearchOutputSchema = z.object({
  query: z.string(),
  matches: z.array(instrumentMatchSchema),
});

export const instrumentAutocompleteOutputSchema = instrumentSearchOutputSchema;

export const instrumentResolveOutputSchema = z
  .object({
    query: z.string(),
    status: z.enum(["resolved", "ambiguous", "not_found"]),
    match: instrumentMatchSchema.nullable().optional(),
    candidates: z.array(instrumentMatchSchema),
  })
  .superRefine((value, context) => {
    if (value.status === "resolved" && !value.match) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        message: "Resolved instruments require a match",
      });
    }
    if (value.status === "ambiguous" && value.candidates.length < 2) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        message: "Ambiguous instruments require at least two candidates",
      });
    }
  });

const decimalSchema = z
  .string()
  .regex(/^-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?$/, "Expected a decimal string");

export const providerMetadataSchema = z.object({
  provider: z.string().min(1),
  source_id: z.string().min(1),
  observed_at: z.string().nullable().optional(),
  retrieved_at: z.string(),
  timezone: z.string().nullable().optional(),
  license: z.enum(["internal", "redistributable", "restricted", "unknown"]),
  freshness: z.enum(["fresh", "stale", "unknown"]),
});

export const cacheMetadataSchema = z.object({
  disposition: z.enum(["hit", "miss"]),
  cached_at: z.string(),
  expires_at: z.string(),
});

export const stockQuoteOutputSchema = z.object({
  instrument: instrumentRefSchema,
  price: decimalSchema,
  currency: z.string(),
  as_of: z.string(),
  previous_close: decimalSchema.nullable().optional(),
  change: decimalSchema.nullable().optional(),
  change_percent: decimalSchema.nullable().optional(),
  open: decimalSchema.nullable().optional(),
  high: decimalSchema.nullable().optional(),
  low: decimalSchema.nullable().optional(),
  volume: decimalSchema.nullable().optional(),
  market_status: z.string().nullable().optional(),
  provider: providerMetadataSchema,
  cache: cacheMetadataSchema,
});

const adjustedPriceBarSchema = z.object({
  timestamp: z.string(),
  open: decimalSchema,
  high: decimalSchema,
  low: decimalSchema,
  close: decimalSchema,
  adjusted_close: decimalSchema,
  volume: decimalSchema.nullable().optional(),
});

export const stockHistoryOutputSchema = z.object({
  instrument: instrumentRefSchema,
  interval: z.enum(["1d", "1wk", "1mo"]),
  price_basis: z.literal("adjusted"),
  currency: z.string(),
  bars: z.array(adjustedPriceBarSchema),
  provider: providerMetadataSchema,
  cache: cacheMetadataSchema,
});

const performanceMetricsSchema = z.object({
  start_at: z.string(),
  end_at: z.string(),
  start_value: decimalSchema,
  end_value: decimalSchema,
  observations: z.number().int().min(2),
  total_return: decimalSchema,
  cagr: decimalSchema,
  annualized_volatility: decimalSchema,
  maximum_drawdown: decimalSchema,
});

const rebasedPointSchema = z.object({
  timestamp: z.string(),
  value: decimalSchema,
});

export const stockPerformanceOutputSchema = z.object({
  instrument: instrumentRefSchema,
  interval: z.enum(["1d", "1wk", "1mo"]),
  currency: z.string(),
  metrics: performanceMetricsSchema,
  series: z.array(rebasedPointSchema),
  provider: providerMetadataSchema,
  cache: cacheMetadataSchema,
});

const stockComparisonItemSchema = stockPerformanceOutputSchema.omit({
  interval: true,
});

export const stockComparisonOutputSchema = z.object({
  start: z.string(),
  end: z.string(),
  interval: z.enum(["1d", "1wk", "1mo"]),
  items: z.array(stockComparisonItemSchema).min(2).max(10),
});

const stockCorporateActionSchema = z.object({
  instrument: instrumentRefSchema,
  action_type: z.enum([
    "dividend",
    "split",
    "spinoff",
    "merger",
    "symbol_change",
    "other",
  ]),
  effective_at: z.string(),
  amount: decimalSchema.nullable().optional(),
  currency: z.string().nullable().optional(),
  ratio: decimalSchema.nullable().optional(),
  provider: providerMetadataSchema,
});

export const stockCorporateActionsOutputSchema = z.object({
  instrument: instrumentRefSchema,
  start: z.string(),
  end: z.string(),
  actions: z.array(stockCorporateActionSchema),
  provider: providerMetadataSchema,
  cache: cacheMetadataSchema,
});

export const fiveYearPerformanceOutputSchema = z.object({
  requested_as_of: z.string(),
  effective_start: z.string(),
  performance: stockPerformanceOutputSchema,
});

export const benchmarkComparisonOutputSchema = z.object({
  instrument: stockComparisonItemSchema,
  benchmark: stockComparisonItemSchema,
  overlapping_observations: z.number().int().min(2),
  excess_total_return: decimalSchema,
  excess_cagr: decimalSchema,
});

export type ResponseComponent = z.infer<typeof responseComponentSchema>;
export type CapabilityDescriptor = z.infer<typeof capabilityDescriptorSchema>;
export type CommandDescriptor = z.infer<typeof commandDescriptorSchema>;
export type Health = z.infer<typeof healthSchema>;
export type CommandResponse = z.infer<typeof commandResponseSchema>;
export type ChatSession = z.infer<typeof chatSessionSchema>;
export type ChatMessage = z.infer<typeof chatMessageSchema>;
export type ChatTurn = z.infer<typeof chatTurnSchema>;
export type ChatSessionDetail = z.infer<typeof chatSessionDetailSchema>;
export type ChatSessionPage = z.infer<typeof chatSessionPageSchema>;
export type ChatTurnAccepted = z.infer<typeof chatTurnAcceptedSchema>;
export type ChatStreamEvent = z.infer<typeof chatStreamEventSchema>;
export type AssetType = z.infer<typeof assetTypeSchema>;
export type InstrumentRef = z.infer<typeof instrumentRefSchema>;
export type InstrumentMatch = z.infer<typeof instrumentMatchSchema>;
export type InstrumentSearchOutput = z.infer<
  typeof instrumentSearchOutputSchema
>;
export type InstrumentAutocompleteOutput = z.infer<
  typeof instrumentAutocompleteOutputSchema
>;
export type InstrumentResolveOutput = z.infer<
  typeof instrumentResolveOutputSchema
>;
export type StockQuoteOutput = z.infer<typeof stockQuoteOutputSchema>;
export type StockHistoryOutput = z.infer<typeof stockHistoryOutputSchema>;
export type StockPerformanceOutput = z.infer<
  typeof stockPerformanceOutputSchema
>;
export type StockComparisonOutput = z.infer<typeof stockComparisonOutputSchema>;
export type StockCorporateActionsOutput = z.infer<
  typeof stockCorporateActionsOutputSchema
>;
export type FiveYearPerformanceOutput = z.infer<
  typeof fiveYearPerformanceOutputSchema
>;
export type BenchmarkComparisonOutput = z.infer<
  typeof benchmarkComparisonOutputSchema
>;
