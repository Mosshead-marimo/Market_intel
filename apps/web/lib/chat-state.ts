import type {
  ChatMessage,
  ChatStreamEvent,
  ResponseComponent,
} from "@tradesentinel/contracts";

export type ChatStreamState = {
  status: string;
  typing: boolean;
  reconnecting: boolean;
  text: string;
  progress: string[];
  components: ResponseComponent[];
  warnings: string[];
  error: string | null;
  completedMessage: ChatMessage | null;
  seen: ReadonlySet<string>;
};

export const initialChatStreamState: ChatStreamState = {
  status: "idle",
  typing: false,
  reconnecting: false,
  text: "",
  progress: [],
  components: [],
  warnings: [],
  error: null,
  completedMessage: null,
  seen: new Set<string>(),
};

export function reduceChatStream(
  state: ChatStreamState,
  event: ChatStreamEvent,
): ChatStreamState {
  if (state.seen.has(event.event_id)) return state;
  const seen = new Set(state.seen).add(event.event_id);
  const base = { ...state, seen, reconnecting: false };
  switch (event.type) {
    case "status":
      return { ...base, status: event.status };
    case "typing":
      return { ...base, typing: event.active };
    case "progress":
      return {
        ...base,
        progress: base.progress.includes(event.label)
          ? base.progress
          : [...base.progress, event.label],
      };
    case "response":
      return { ...base, text: base.text + event.delta };
    case "component":
      return { ...base, components: [...base.components, event.component] };
    case "warning":
      return { ...base, warnings: [...base.warnings, event.warning.message] };
    case "complete":
      return {
        ...base,
        status: event.turn.status,
        typing: false,
        completedMessage: event.message,
      };
    case "error":
      return {
        ...base,
        status: "failed",
        typing: false,
        error: event.error.message,
      };
  }
}
