import { EvidenceWorkspace } from "@/components/evidence-workspace";

export default async function EvidencePage({
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
    <EvidenceWorkspace
      query={decodeURIComponent(instrument)}
      exchange={exchange}
    />
  );
}
