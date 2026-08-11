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

export const priceChartSchema = componentBase.extend({
  type: z.literal("price_chart"),
  ...chartSchema.shape,
});
export const sentimentChartSchema = componentBase.extend({
  type: z.literal("sentiment_chart"),
  ...chartSchema.shape,
});
export const newsTimelineSchema = componentBase.extend({
  type: z.literal("news_timeline"),
  items: z.array(
    z.object({
      occurred_at: z.string(),
      headline: z.string(),
      description: z.string().nullable().optional(),
      source_id: z.string().nullable().optional(),
    }),
  ),
});
export const eventTimelineSchema = componentBase.extend({
  type: z.literal("event_timeline"),
  items: z.array(
    z.object({
      occurred_at: z.string(),
      label: z.string(),
      description: z.string().nullable().optional(),
      category: z.string().nullable().optional(),
      source_id: z.string().nullable().optional(),
    }),
  ),
});
const predictionCardSchema = componentBase.extend({
  type: z.literal("prediction_card"),
  direction: z.enum(["rise", "sideways", "decline", "uncertain"]),
  confidence: z.number().min(0).max(1),
  horizon: z.string(),
  generated_at: z.string(),
  data_cutoff: z.string(),
  model_version: z.string(),
});
const scenarioTableSchema = componentBase.extend({
  type: z.literal("scenario_table"),
  ...tableSchema.shape,
});
const comparisonTableSchema = componentBase.extend({
  type: z.literal("comparison_table"),
  ...tableSchema.shape,
});
const riskCardSchema = componentBase.extend({
  type: z.literal("risk_card"),
  risks: z.array(
    z.object({
      label: z.string(),
      severity: z.enum(["low", "medium", "high", "unknown"]),
      description: z.string(),
    }),
  ),
});
const sourceListSchema = componentBase.extend({
  type: z.literal("source_list"),
  sources: z.array(z.record(z.unknown())),
});
const warningBannerSchema = componentBase.extend({
  type: z.literal("warning_banner"),
  code: z.string(),
  message: z.string(),
});

export const leafResponseComponentSchema = z.discriminatedUnion("type", [
  summaryCardSchema,
  metricGridSchema,
  priceChartSchema,
  sentimentChartSchema,
  newsTimelineSchema,
  eventTimelineSchema,
  predictionCardSchema,
  scenarioTableSchema,
  comparisonTableSchema,
  riskCardSchema,
  sourceListSchema,
  warningBannerSchema,
]);

export const responseSectionSchema = componentBase.extend({
  type: z.literal("response_section"),
  description: z.string().nullable().optional(),
  items: z.array(leafResponseComponentSchema),
});

export const responseComponentSchema = z.discriminatedUnion("type", [
  ...leafResponseComponentSchema.options,
  responseSectionSchema,
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

export const workflowPresentationSectionSchema = z.object({
  id: z.string(),
  title: z.string(),
  steps: z.array(z.string()).min(1),
  empty_message: z.string().nullable().optional(),
  error_message: z.string().nullable().optional(),
});

export const workflowPresentationSchema = z.object({
  title: z.string(),
  completion_event: z.string().nullable().optional(),
  sections: z.array(workflowPresentationSectionSchema).min(1),
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
  presentation: workflowPresentationSchema.nullable().optional(),
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

export const technicalParametersSchema = z
  .object({
    rsi_period: z.number().int().min(2).max(200),
    macd_fast_period: z.number().int().min(2).max(200),
    macd_slow_period: z.number().int().min(3).max(400),
    macd_signal_period: z.number().int().min(2).max(200),
    ema_period: z.number().int().min(2).max(400),
    sma_period: z.number().int().min(2).max(400),
    atr_period: z.number().int().min(2).max(200),
    adx_period: z.number().int().min(2).max(200),
    momentum_roc_period: z.number().int().min(1).max(200),
    volatility_period: z.number().int().min(2).max(200),
    trend_fast_period: z.number().int().min(2).max(200),
    trend_slow_period: z.number().int().min(3).max(400),
    level_lookback: z.number().int().min(5).max(500),
    pivot_span: z.number().int().min(1).max(20),
    pivot_max_levels: z.number().int().min(1).max(10),
    pivot_atr_multiplier: decimalSchema,
    trend_spread_threshold: decimalSchema,
    momentum_rsi_lower: decimalSchema,
    momentum_rsi_upper: decimalSchema,
    volatility_low_percentile: decimalSchema,
    volatility_high_percentile: decimalSchema,
  })
  .strict();

const technicalIndicatorPointSchema = z
  .object({ timestamp: z.string(), value: decimalSchema })
  .strict();
const technicalIndicatorSeriesSchema = z
  .object({
    period: z.number().int().positive(),
    latest: decimalSchema,
    points: z.array(technicalIndicatorPointSchema),
  })
  .strict();
const technicalSeriesOutputBase = z
  .object({
    instrument: instrumentRefSchema,
    interval: z.enum(["1d", "1wk", "1mo"]),
    series: technicalIndicatorSeriesSchema,
  })
  .strict();

export const technicalRsiOutputSchema = technicalSeriesOutputBase;
export const technicalEmaOutputSchema = technicalSeriesOutputBase;
export const technicalSmaOutputSchema = technicalSeriesOutputBase;
export const technicalAtrOutputSchema = technicalSeriesOutputBase;

const macdPointSchema = z
  .object({
    timestamp: z.string(),
    macd: decimalSchema,
    signal: decimalSchema,
    histogram: decimalSchema,
  })
  .strict();
export const technicalMacdOutputSchema = z
  .object({
    instrument: instrumentRefSchema,
    interval: z.enum(["1d", "1wk", "1mo"]),
    fast_period: z.number().int().positive(),
    slow_period: z.number().int().positive(),
    signal_period: z.number().int().positive(),
    latest: macdPointSchema,
    points: z.array(macdPointSchema),
  })
  .strict();

const adxPointSchema = z
  .object({
    timestamp: z.string(),
    adx: decimalSchema,
    positive_di: decimalSchema,
    negative_di: decimalSchema,
  })
  .strict();
export const technicalAdxOutputSchema = z
  .object({
    instrument: instrumentRefSchema,
    interval: z.enum(["1d", "1wk", "1mo"]),
    period: z.number().int().positive(),
    latest: adxPointSchema,
    points: z.array(adxPointSchema),
  })
  .strict();

const priceLevelSchema = z
  .object({
    method: z.enum(["rolling_extreme", "pivot_cluster"]),
    level: decimalSchema,
    touches: z.number().int().positive(),
    first_tested_at: z.string(),
    last_tested_at: z.string(),
    distance_percent: decimalSchema,
  })
  .strict();
export const technicalLevelOutputSchema = z
  .object({
    instrument: instrumentRefSchema,
    interval: z.enum(["1d", "1wk", "1mo"]),
    side: z.enum(["support", "resistance"]),
    current_price: decimalSchema,
    lookback: z.number().int().positive(),
    levels: z.array(priceLevelSchema),
  })
  .strict();

export const technicalTrendOutputSchema = z
  .object({
    instrument: instrumentRefSchema,
    interval: z.enum(["1d", "1wk", "1mo"]),
    direction: z.enum(["rising", "falling", "sideways"]),
    strength: z.enum(["weak", "developing", "strong"]),
    fast_ema: decimalSchema,
    slow_ema: decimalSchema,
    spread_percent: decimalSchema,
    adx: decimalSchema,
  })
  .strict();

export const technicalMomentumOutputSchema = z
  .object({
    instrument: instrumentRefSchema,
    interval: z.enum(["1d", "1wk", "1mo"]),
    direction: z.enum(["positive", "neutral", "negative"]),
    positive_votes: z.number().int().min(0).max(3),
    negative_votes: z.number().int().min(0).max(3),
    rsi: decimalSchema,
    macd_histogram: decimalSchema,
    rate_of_change: decimalSchema,
  })
  .strict();

export const technicalVolatilityOutputSchema = z
  .object({
    instrument: instrumentRefSchema,
    interval: z.enum(["1d", "1wk", "1mo"]),
    regime: z.enum(["low", "normal", "high", "unknown"]),
    period: z.number().int().positive(),
    annualized_volatility: decimalSchema,
    atr_percent: decimalSchema,
    percentile_rank: decimalSchema.nullable().optional(),
    rolling: z.array(technicalIndicatorPointSchema),
  })
  .strict();

export const technicalSnapshotSchema = z
  .object({
    instrument: instrumentRefSchema,
    status: z.enum(["completed", "partial", "empty"]),
    interval: z.enum(["1d", "1wk", "1mo"]),
    requested_start: z.string(),
    requested_end: z.string(),
    observed_start: z.string().nullable().optional(),
    observed_end: z.string().nullable().optional(),
    data_cutoff: z.string().nullable().optional(),
    observation_count: z.number().int().nonnegative(),
    price_basis: z.literal("adjusted_ohlc"),
    calculation_version: z.literal("technical-v1"),
    parameters: technicalParametersSchema,
    provider: providerMetadataSchema,
    cache: cacheMetadataSchema,
    warnings: z.array(z.string()),
    rsi: technicalRsiOutputSchema.nullable().optional(),
    macd: technicalMacdOutputSchema.nullable().optional(),
    ema: technicalEmaOutputSchema.nullable().optional(),
    sma: technicalSmaOutputSchema.nullable().optional(),
    atr: technicalAtrOutputSchema.nullable().optional(),
    adx: technicalAdxOutputSchema.nullable().optional(),
    support: technicalLevelOutputSchema.nullable().optional(),
    resistance: technicalLevelOutputSchema.nullable().optional(),
    trend: technicalTrendOutputSchema.nullable().optional(),
    momentum: technicalMomentumOutputSchema.nullable().optional(),
    volatility: technicalVolatilityOutputSchema.nullable().optional(),
  })
  .strict();

export const researchSourceSchema = z.object({
  source_id: z.string().min(1),
  provider_source_id: z.string().min(1),
  provider: z.string().min(1),
  title: z.string().min(1),
  url: z.string().url(),
  published_at: z.string().nullable().optional(),
  retrieved_at: z.string(),
  timestamp: z.string(),
  timestamp_basis: z.enum(["published", "retrieved"]),
  summary: z.string().nullable().optional(),
  document_hash: z
    .string()
    .regex(/^[0-9a-f]{64}$/)
    .nullable()
    .optional(),
  license: z.string(),
  freshness: z.string(),
  untrusted: z.literal(true),
});

export const researchClaimSchema = z.object({
  claim_id: z.string().uuid(),
  event_id: z.string().uuid(),
  text: z.string().min(1),
  source: researchSourceSchema,
  provider: z.string().min(1),
  timestamp: z.string(),
  timestamp_basis: z.enum(["published", "retrieved"]),
  confidence: z.number().min(0).max(1),
  confidence_basis: z.enum([
    "strong_title_phrase",
    "title_rule",
    "summary_rule",
    "document_rule",
  ]),
  extraction_version: z.string().min(1),
  evidence_excerpt: z.string().min(1),
});

export const researchEventSchema = z.object({
  event_id: z.string().uuid(),
  query: z.string(),
  event_type: z.enum([
    "earnings",
    "guidance",
    "dividend",
    "merger_acquisition",
    "leadership",
    "product",
    "partnership",
    "financing",
    "regulatory_legal",
    "operations",
    "other",
  ]),
  headline: z.string().min(1),
  observed_at: z.string(),
  timestamp_basis: z.enum(["published", "retrieved"]),
  confidence: z.number().min(0).max(1),
  extraction_version: z.string().min(1),
  claims: z.array(researchClaimSchema).min(1),
  source_ids: z.array(z.string()).min(1),
});

export const duplicateGroupSchema = z.object({
  representative_source_id: z.string(),
  duplicate_source_ids: z.array(z.string()),
  reason: z.enum([
    "provider_source",
    "canonical_url",
    "document_hash",
    "title_day",
  ]),
});

export const newsSearchOutputSchema = z.object({
  query: z.string(),
  sources: z.array(researchSourceSchema),
});

export const researchTimelineOutputSchema = z.object({
  query: z.string(),
  events: z.array(researchEventSchema),
});

export const researchEvidenceOutputSchema = z.object({
  event: researchEventSchema,
  sources: z.array(researchSourceSchema),
  claims: z.array(researchClaimSchema),
});

export const researchReportOutputSchema = z.object({
  query: z.string(),
  status: z.enum(["completed", "partial", "empty"]),
  coverage: z.object({
    source_count: z.number().int().nonnegative(),
    duplicate_count: z.number().int().nonnegative(),
    event_count: z.number().int().nonnegative(),
    claim_count: z.number().int().nonnegative(),
    unmatched_count: z.number().int().nonnegative(),
    document_failure_count: z.number().int().nonnegative(),
  }),
  events: z.array(researchEventSchema),
  sources: z.array(researchSourceSchema),
  duplicate_groups: z.array(duplicateGroupSchema),
  warnings: z.array(z.string()),
});

export const sentimentLabelSchema = z.enum([
  "positive",
  "neutral",
  "negative",
  "unknown",
]);

const sentimentEvidenceSchema = z.object({
  source_id: z.string(),
  provider: z.string(),
  source_type: z.string(),
  observed_at: z.string(),
  retrieved_at: z.string(),
  url: z.string().url().nullable().optional(),
  untrusted: z.literal(true),
});

const sentimentSignalSchema = z.object({
  label: sentimentLabelSchema,
  score: decimalSchema.nullable().optional(),
  confidence: decimalSchema.nullable().optional(),
  method: z.enum(["provider", "lexicon", "none"]),
  version: z.string(),
  positive_hits: z.number().int().nonnegative(),
  negative_hits: z.number().int().nonnegative(),
});

export const discussionSchema = z.object({
  discussion_id: z.string().uuid(),
  provider_source_id: z.string(),
  text_excerpt: z.string(),
  content_hash: z.string().regex(/^[0-9a-f]{64}$/),
  occurred_at: z.string(),
  author_hash: z
    .string()
    .regex(/^[0-9a-f]{64}$/)
    .nullable()
    .optional(),
  language: z.string(),
  engagement_count: z.number().int().nonnegative(),
  provider_spam: z.boolean(),
  evidence: sentimentEvidenceSchema,
  signal: sentimentSignalSchema,
});

const windowMetricsSchema = z.object({
  start: z.string(),
  end: z.string(),
  mention_count: z.number().int().nonnegative(),
  usable_count: z.number().int().nonnegative(),
  positive_share: decimalSchema.nullable().optional(),
  neutral_share: decimalSchema.nullable().optional(),
  negative_share: decimalSchema.nullable().optional(),
  mean_score: decimalSchema.nullable().optional(),
  agreement: decimalSchema.nullable().optional(),
  mean_signal_confidence: decimalSchema.nullable().optional(),
});

export const sentimentSnapshotSchema = z.object({
  snapshot_id: z.string().uuid(),
  target: instrumentRefSchema,
  status: z.enum(["completed", "partial", "empty", "insufficient"]),
  as_of: z.string(),
  current: windowMetricsSchema,
  previous: windowMetricsSchema,
  volume_change: decimalSchema.nullable().optional(),
  confidence: decimalSchema.nullable().optional(),
  co_mentions: z.array(instrumentRefSchema),
  warnings: z.array(z.string()),
  lexicon_version: z.string(),
});

export const sentimentNarrativeSchema = z.object({
  narrative_id: z.string().uuid(),
  topic: z.string(),
  method: z.enum(["taxonomy", "ngram"]),
  sentiment: sentimentLabelSchema,
  weighted_share: decimalSchema,
  mention_count: z.number().int().positive(),
  confidence: decimalSchema,
  discussion_ids: z.array(z.string().uuid()),
  providers: z.array(z.string()),
  observation_timestamps: z.array(z.string()),
});

export const sentimentTrendSchema = z.object({
  target: instrumentRefSchema,
  status: z.enum(["completed", "partial", "empty", "insufficient"]),
  direction: z.enum(["improving", "stable", "deteriorating", "insufficient"]),
  slope: decimalSchema.nullable().optional(),
  acceleration: decimalSchema.nullable().optional(),
  buckets: z.array(
    z.object({
      day: z.string(),
      mention_count: z.number().int().nonnegative(),
      mean_score: decimalSchema.nullable().optional(),
    }),
  ),
});

export const sentimentShiftSchema = z
  .object({
    target: instrumentRefSchema,
    status: z.enum(["completed", "partial", "empty", "insufficient"]),
    shift_score: decimalSchema.nullable().optional(),
    sentiment_component: decimalSchema.nullable().optional(),
    volume_component: decimalSchema.nullable().optional(),
    description: z.string(),
  })
  .strict();

export const publicSentimentAnalysisSchema = z.object({
  snapshot: sentimentSnapshotSchema,
  narratives: z.object({
    target: instrumentRefSchema,
    status: z.enum(["completed", "partial", "empty", "insufficient"]),
    narratives: z.array(sentimentNarrativeSchema),
  }),
  trend: sentimentTrendSchema,
  shift: sentimentShiftSchema,
});

export const fundamentalStatusSchema = z.enum([
  "completed",
  "partial",
  "empty",
]);

const fundamentalPointSchema = z.object({
  period_type: z.enum(["annual", "quarterly"]),
  period_start: z.string().nullable().optional(),
  period_end: z.string(),
  filed_at: z.string().nullable().optional(),
  value: decimalSchema.nullable(),
  unit: z.string(),
  currency: z.string().nullable().optional(),
  provider: providerMetadataSchema,
});

const fundamentalMetricSchema = z.object({
  concept: z.string(),
  label: z.string(),
  unit: z.string(),
  latest: decimalSchema.nullable().optional(),
  annual: z.array(fundamentalPointSchema),
  quarterly: z.array(fundamentalPointSchema),
});

export const fundamentalSectionSchema = z.object({
  instrument: instrumentRefSchema,
  section: z.enum([
    "revenue",
    "profit",
    "cash_flow",
    "debt",
    "margins",
    "roe",
    "roce",
  ]),
  status: fundamentalStatusSchema,
  as_of: z.string(),
  metrics: z.array(fundamentalMetricSchema),
  warnings: z.array(z.string()),
  data_cutoff: z.string().nullable().optional(),
});

export const fundamentalGrowthSchema = z.object({
  instrument: instrumentRefSchema,
  status: fundamentalStatusSchema,
  as_of: z.string(),
  metrics: z.array(
    z.object({
      concept: z.string(),
      annual_yoy: z.array(z.record(z.unknown())),
      quarterly_yoy: z.array(z.record(z.unknown())),
      quarterly_qoq: z.array(z.record(z.unknown())),
      annual_cagr: decimalSchema.nullable().optional(),
    }),
  ),
  warnings: z.array(z.string()),
  data_cutoff: z.string().nullable().optional(),
});

export const fundamentalValuationSchema = z.object({
  instrument: instrumentRefSchema,
  status: fundamentalStatusSchema,
  as_of: z.string(),
  currency: z.string().nullable().optional(),
  metrics: z.array(
    z.object({
      concept: z.string(),
      calculated: decimalSchema.nullable().optional(),
      reported: decimalSchema.nullable().optional(),
      historical_reported: z.array(fundamentalPointSchema),
    }),
  ),
  warnings: z.array(z.string()),
  data_cutoff: z.string().nullable().optional(),
});

const companyProfileSchema = z.object({
  instrument: z.object({ symbol: z.string(), exchange: z.string() }),
  legal_name: z.string(),
  sector: z.string().nullable().optional(),
  industry: z.string().nullable().optional(),
  reporting_currency: z.string().nullable().optional(),
  metadata: providerMetadataSchema,
});

export const fundamentalSnapshotSchema = z
  .object({
    instrument: instrumentRefSchema,
    status: fundamentalStatusSchema,
    as_of: z.string(),
    data_cutoff: z.string().nullable().optional(),
    calculation_version: z.literal("fundamentals-v1"),
    profile: companyProfileSchema,
    revenue: fundamentalSectionSchema,
    profit: fundamentalSectionSchema,
    cash_flow: fundamentalSectionSchema,
    debt: fundamentalSectionSchema,
    margins: fundamentalSectionSchema,
    roe: fundamentalSectionSchema,
    roce: fundamentalSectionSchema,
    valuation: fundamentalValuationSchema,
    growth: fundamentalGrowthSchema,
    warnings: z.array(z.string()),
  })
  .strict();

export const fundamentalPeerComparisonSchema = z
  .object({
    target: instrumentRefSchema,
    peers: z.array(instrumentRefSchema).min(1).max(9),
    status: fundamentalStatusSchema,
    as_of: z.string(),
    comparisons: z.array(
      z.object({
        concept: z.string(),
        median: decimalSchema.nullable(),
        values: z.array(
          z.object({
            instrument: instrumentRefSchema,
            value: decimalSchema.nullable(),
            percentile: decimalSchema.nullable().optional(),
          }),
        ),
      }),
    ),
    warnings: z.array(z.string()),
  })
  .strict();

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
export type TechnicalParameters = z.infer<typeof technicalParametersSchema>;
export type TechnicalRsiOutput = z.infer<typeof technicalRsiOutputSchema>;
export type TechnicalMacdOutput = z.infer<typeof technicalMacdOutputSchema>;
export type TechnicalEmaOutput = z.infer<typeof technicalEmaOutputSchema>;
export type TechnicalSmaOutput = z.infer<typeof technicalSmaOutputSchema>;
export type TechnicalAtrOutput = z.infer<typeof technicalAtrOutputSchema>;
export type TechnicalAdxOutput = z.infer<typeof technicalAdxOutputSchema>;
export type TechnicalLevelOutput = z.infer<typeof technicalLevelOutputSchema>;
export type TechnicalTrendOutput = z.infer<typeof technicalTrendOutputSchema>;
export type TechnicalMomentumOutput = z.infer<
  typeof technicalMomentumOutputSchema
>;
export type TechnicalVolatilityOutput = z.infer<
  typeof technicalVolatilityOutputSchema
>;
export type TechnicalSnapshot = z.infer<typeof technicalSnapshotSchema>;
export type ResearchSource = z.infer<typeof researchSourceSchema>;
export type ResearchClaim = z.infer<typeof researchClaimSchema>;
export type ResearchEvent = z.infer<typeof researchEventSchema>;
export type NewsSearchOutput = z.infer<typeof newsSearchOutputSchema>;
export type ResearchTimelineOutput = z.infer<
  typeof researchTimelineOutputSchema
>;
export type ResearchEvidenceOutput = z.infer<
  typeof researchEvidenceOutputSchema
>;
export type ResearchReportOutput = z.infer<typeof researchReportOutputSchema>;
export type Discussion = z.infer<typeof discussionSchema>;
export type SentimentSnapshot = z.infer<typeof sentimentSnapshotSchema>;
export type SentimentNarrative = z.infer<typeof sentimentNarrativeSchema>;
export type SentimentTrend = z.infer<typeof sentimentTrendSchema>;
export type SentimentShift = z.infer<typeof sentimentShiftSchema>;
export type PublicSentimentAnalysis = z.infer<
  typeof publicSentimentAnalysisSchema
>;
export type FundamentalSection = z.infer<typeof fundamentalSectionSchema>;
export type FundamentalGrowth = z.infer<typeof fundamentalGrowthSchema>;
export type FundamentalValuation = z.infer<typeof fundamentalValuationSchema>;
export type FundamentalSnapshot = z.infer<typeof fundamentalSnapshotSchema>;
export type FundamentalPeerComparison = z.infer<
  typeof fundamentalPeerComparisonSchema
>;
