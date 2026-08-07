import {
  capabilityDescriptorSchema,
  chatSessionDetailSchema,
  chatSessionPageSchema,
  chatSessionSchema,
  chatStreamEventSchema,
  chatTurnAcceptedSchema,
  commandDescriptorSchema,
  healthSchema,
  type CapabilityDescriptor,
  type ChatSession,
  type ChatSessionDetail,
  type ChatSessionPage,
  type ChatStreamEvent,
  type ChatTurnAccepted,
  type CommandDescriptor,
  type Health,
} from "@tradesentinel/contracts";

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function request(path: string, init?: RequestInit): Promise<unknown> {
  const response = await fetch(`${apiUrl}${path}`, {
    cache: "no-store",
    credentials: "include",
    ...init,
    headers: {
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as {
      error?: { message?: string };
    } | null;
    throw new Error(
      body?.error?.message ?? `Request failed with status ${response.status}`,
    );
  }
  return response.json();
}

export async function getHealth(): Promise<Health> {
  return healthSchema.parse(await request("/health/ready"));
}

export async function getCapabilities(): Promise<CapabilityDescriptor[]> {
  return capabilityDescriptorSchema
    .array()
    .parse(await request("/api/v1/capabilities"));
}

export async function getCommands(): Promise<CommandDescriptor[]> {
  return commandDescriptorSchema
    .array()
    .parse(await request("/api/v1/commands"));
}

export async function listSessions(archived = false): Promise<ChatSessionPage> {
  return chatSessionPageSchema.parse(
    await request(`/api/v1/chat/sessions?archived=${archived}`),
  );
}

export async function createSession(title = "New chat"): Promise<ChatSession> {
  return chatSessionSchema.parse(
    await request("/api/v1/chat/sessions", {
      method: "POST",
      body: JSON.stringify({ title }),
    }),
  );
}

export async function getSession(id: string): Promise<ChatSessionDetail> {
  return chatSessionDetailSchema.parse(
    await request(`/api/v1/chat/sessions/${id}`),
  );
}

export async function updateSession(
  id: string,
  change: { title?: string; archived?: boolean },
): Promise<ChatSession> {
  return chatSessionSchema.parse(
    await request(`/api/v1/chat/sessions/${id}`, {
      method: "PATCH",
      body: JSON.stringify(change),
    }),
  );
}

export async function sendMessage(input: {
  message: string;
  sessionId?: string;
  clientMessageId: string;
}): Promise<ChatTurnAccepted> {
  return chatTurnAcceptedSchema.parse(
    await request("/api/v1/chat", {
      method: "POST",
      body: JSON.stringify({
        message: input.message,
        session_id: input.sessionId,
        client_message_id: input.clientMessageId,
      }),
    }),
  );
}

export function subscribeToTurn(
  streamUrl: string,
  handlers: {
    event: (event: ChatStreamEvent) => void;
    reconnecting: () => void;
  },
): () => void {
  const source = new EventSource(`${apiUrl}${streamUrl}`, {
    withCredentials: true,
  });
  const onMessage = (raw: Event) => {
    if (!(raw instanceof MessageEvent)) return;
    const parsed = chatStreamEventSchema.safeParse(JSON.parse(raw.data));
    if (parsed.success) {
      handlers.event(parsed.data);
      if (parsed.data.type === "complete" || parsed.data.type === "error") {
        source.close();
      }
    }
  };
  for (const name of [
    "status",
    "typing",
    "progress",
    "response",
    "component",
    "warning",
    "complete",
    "error",
  ]) {
    source.addEventListener(name, onMessage);
  }
  source.onerror = handlers.reconnecting;
  return () => source.close();
}
