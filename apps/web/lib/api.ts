import {
  capabilityDescriptorSchema,
  commandDescriptorSchema,
  commandResponseSchema,
  healthSchema,
  type CapabilityDescriptor,
  type CommandDescriptor,
  type CommandResponse,
  type Health,
} from "@tradesentinel/contracts";

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function getJson(path: string): Promise<unknown> {
  const response = await fetch(`${apiUrl}${path}`, { cache: "no-store" });
  if (!response.ok)
    throw new Error(`Request failed with status ${response.status}`);
  return response.json();
}

export async function getHealth(): Promise<Health> {
  return healthSchema.parse(await getJson("/health/ready"));
}

export async function getCapabilities(): Promise<CapabilityDescriptor[]> {
  return capabilityDescriptorSchema
    .array()
    .parse(await getJson("/api/v1/capabilities"));
}

export async function getCommands(): Promise<CommandDescriptor[]> {
  return commandDescriptorSchema
    .array()
    .parse(await getJson("/api/v1/commands"));
}

export async function executeCommand(
  command: string,
): Promise<CommandResponse> {
  const response = await fetch(`${apiUrl}/api/v1/commands/execute`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ command }),
  });
  if (!response.ok)
    throw new Error(`Command failed with status ${response.status}`);
  return commandResponseSchema.parse(await response.json());
}

export function subscribeToEvents(
  onEvent: (event: MessageEvent<string>) => void,
): () => void {
  const stream = new EventSource(`${apiUrl}/api/v1/events/stream`);
  for (const type of [
    "status",
    "component",
    "warning",
    "response",
    "complete",
    "error",
  ])
    stream.addEventListener(type, onEvent as EventListener);
  return () => stream.close();
}
