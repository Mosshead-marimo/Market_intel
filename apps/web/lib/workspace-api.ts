import {
  fundamentalSnapshotSchema,
  instrumentAutocompleteOutputSchema,
  instrumentResolveOutputSchema,
  marketShiftHistoryPageSchema,
  marketShiftSnapshotSchema,
  marketShiftWatchlistSchema,
  modelPerformanceReportSchema,
  publicSentimentAnalysisSchema,
  renderedResponseSchema,
  researchReportOutputSchema,
  stockCorporateActionsOutputSchema,
  stockHistoryOutputSchema,
  stockPerformanceOutputSchema,
  stockQuoteOutputSchema,
  technicalSnapshotSchema,
  type FundamentalSnapshot,
  type InstrumentAutocompleteOutput,
  type InstrumentRef,
  type InstrumentResolveOutput,
  type MarketShiftHistoryPage,
  type MarketShiftSnapshot,
  type MarketShiftWatchlist,
  type ModelPerformanceReport,
  type PublicSentimentAnalysis,
  type RenderedResponse,
  type ResearchReportOutput,
  type StockCorporateActionsOutput,
  type StockHistoryOutput,
  type StockPerformanceOutput,
  type StockQuoteOutput,
  type TechnicalSnapshot,
} from "@tradesentinel/contracts";
import { z } from "zod";
import { apiRequest } from "./api";

const marketBundleSchema = z.object({
  quote: stockQuoteOutputSchema,
  history: stockHistoryOutputSchema,
  performance: stockPerformanceOutputSchema,
  actions: stockCorporateActionsOutputSchema,
});

export type MarketBundle = {
  quote: StockQuoteOutput;
  history: StockHistoryOutput;
  performance: StockPerformanceOutput;
  actions: StockCorporateActionsOutput;
};

function post(path: string, body: unknown, token?: string): Promise<unknown> {
  return apiRequest(path, {
    method: "POST",
    body: JSON.stringify(body),
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  });
}

export async function autocompleteInstrument(
  query: string,
): Promise<InstrumentAutocompleteOutput> {
  return instrumentAutocompleteOutputSchema.parse(
    await apiRequest(
      `/api/v1/instruments/autocomplete?q=${encodeURIComponent(query)}&limit=8`,
    ),
  );
}

export async function resolveInstrument(
  query: string,
  exchange?: string,
): Promise<InstrumentResolveOutput> {
  const suffix = exchange ? `&exchange=${encodeURIComponent(exchange)}` : "";
  return instrumentResolveOutputSchema.parse(
    await apiRequest(
      `/api/v1/instruments/resolve?q=${encodeURIComponent(query)}${suffix}`,
    ),
  );
}

export async function loadOverview(
  instrument: InstrumentRef,
): Promise<RenderedResponse> {
  return renderedResponseSchema.parse(
    await post("/api/v1/stock-overview", {
      query: instrument.symbol,
      exchange: instrument.exchange,
    }),
  );
}

export async function loadMarket(
  instrument: InstrumentRef,
): Promise<MarketBundle> {
  const end = new Date();
  const start = new Date(end);
  start.setUTCFullYear(start.getUTCFullYear() - 1);
  const range = {
    instrument,
    start: start.toISOString(),
    end: end.toISOString(),
    interval: "1d",
  };
  const [quote, history, performance, actions] = await Promise.all([
    post("/api/v1/market-data/quote", { instrument }),
    post("/api/v1/market-data/history", range),
    post("/api/v1/market-data/performance", range),
    post("/api/v1/market-data/corporate-actions", {
      instrument,
      start: range.start,
      end: range.end,
    }),
  ]);
  return marketBundleSchema.parse({ quote, history, performance, actions });
}

export async function loadResearch(
  instrument: InstrumentRef,
): Promise<ResearchReportOutput> {
  return researchReportOutputSchema.parse(
    await post("/api/v1/research/reports", { query: instrument.name }),
  );
}

export async function loadSentiment(
  instrument: InstrumentRef,
): Promise<PublicSentimentAnalysis> {
  return publicSentimentAnalysisSchema.parse(
    await post("/api/v1/sentiment/analyze", {
      query: instrument.symbol,
      exchange: instrument.exchange,
    }),
  );
}

export async function loadTechnical(
  instrument: InstrumentRef,
): Promise<TechnicalSnapshot> {
  return technicalSnapshotSchema.parse(
    await post("/api/v1/technical/snapshot", {
      query: instrument.symbol,
      exchange: instrument.exchange,
    }),
  );
}

export async function loadFundamentals(
  instrument: InstrumentRef,
): Promise<FundamentalSnapshot> {
  return fundamentalSnapshotSchema.parse(
    await post("/api/v1/fundamentals/snapshot", {
      query: instrument.symbol,
      exchange: instrument.exchange,
    }),
  );
}

export async function loadMarketShift(
  instrument: InstrumentRef,
): Promise<MarketShiftSnapshot> {
  return marketShiftSnapshotSchema.parse(
    await post("/api/v1/market-shift", {
      query: instrument.symbol,
      exchange: instrument.exchange,
      window_days: 90,
    }),
  );
}

export async function loadMarketShiftHistory(
  instrumentId: string,
): Promise<MarketShiftHistoryPage> {
  return marketShiftHistoryPageSchema.parse(
    await apiRequest(
      `/api/v1/market-shift/instruments/${instrumentId}/history`,
    ),
  );
}

export async function loadMarketShiftWatchlist(
  token: string,
): Promise<MarketShiftWatchlist> {
  return marketShiftWatchlistSchema.parse(
    await apiRequest("/api/v1/admin/market-shift/watchlist", {
      headers: { Authorization: `Bearer ${token}` },
    }),
  );
}

export async function ingestMarketShiftObservations(
  token: string,
  batch: unknown,
): Promise<unknown> {
  return post("/api/v1/admin/market-shift/observations", batch, token);
}

export async function runMarketShiftSchedule(
  token: string,
): Promise<{ processed: number }> {
  return z
    .object({ processed: z.number().int().nonnegative() })
    .parse(await post("/api/v1/admin/market-shift/run", {}, token));
}

const predictionAdminPageSchema = z.object({
  items: z.array(z.record(z.unknown())),
});

export async function loadPredictionAdmin(
  token: string,
  resource: "models" | "predictions",
): Promise<z.infer<typeof predictionAdminPageSchema>> {
  const raw = await apiRequest(`/api/v1/admin/prediction/${resource}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (resource === "models") {
    const models = z
      .object({ models: z.array(z.record(z.unknown())) })
      .parse(raw);
    return { items: models.models };
  }
  return predictionAdminPageSchema.parse(raw);
}

export type PerformanceQuery = {
  modelVersion?: string;
  horizon?: 5 | 20;
  assetType?: string;
  exchange?: string;
  sector?: string;
  start?: string;
  end?: string;
};

export async function loadModelPerformance(
  token: string,
  filters: PerformanceQuery = {},
): Promise<ModelPerformanceReport> {
  const query = new URLSearchParams();
  if (filters.modelVersion) query.set("model_version", filters.modelVersion);
  if (filters.horizon) query.set("horizon_sessions", String(filters.horizon));
  if (filters.assetType) query.set("asset_type", filters.assetType);
  if (filters.exchange) query.set("exchange", filters.exchange);
  if (filters.sector) query.set("sector", filters.sector);
  if (filters.start) query.set("start", new Date(filters.start).toISOString());
  if (filters.end) query.set("end", new Date(filters.end).toISOString());
  const suffix = query.size ? `?${query.toString()}` : "";
  return modelPerformanceReportSchema.parse(
    await apiRequest(`/api/v1/admin/prediction/model-performance${suffix}`, {
      headers: { Authorization: `Bearer ${token}` },
    }),
  );
}

export async function rebuildModelPerformance(token: string): Promise<void> {
  await post("/api/v1/admin/prediction/model-performance/rebuild", {}, token);
}
