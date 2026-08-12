import { InstrumentWorkspace } from "@/components/workspace";

export default async function InstrumentPage({
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
    <InstrumentWorkspace
      query={decodeURIComponent(instrument)}
      exchange={exchange}
    />
  );
}
