import { MarketShiftHistoryView } from "@/components/market-shift-history";

export default async function MarketShiftHistoryPage({
  params,
  searchParams,
}: {
  params: Promise<{ instrument: string }>;
  searchParams: Promise<{ exchange?: string }>;
}) {
  const [{ instrument }, { exchange }] = await Promise.all([
    params,
    searchParams,
  ]);
  return (
    <MarketShiftHistoryView
      query={decodeURIComponent(instrument)}
      exchange={exchange}
    />
  );
}
