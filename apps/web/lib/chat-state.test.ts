import { describe, expect, it } from "vitest";
import type { ChatStreamEvent } from "@tradesentinel/contracts";
import { initialChatStreamState, reduceChatStream } from "./chat-state";

const identifiers = {
  session_id: "11111111-1111-4111-8111-111111111111",
  turn_id: "22222222-2222-4222-8222-222222222222",
  request_id: "33333333-3333-4333-8333-333333333333",
  correlation_id: "44444444-4444-4444-8444-444444444444",
};

type EventInput<T> = T extends ChatStreamEvent
  ? Omit<T, keyof typeof identifiers | "version" | "sequence" | "occurred_at">
  : never;

function event(value: EventInput<ChatStreamEvent>): ChatStreamEvent {
  return {
    ...identifiers,
    version: "1.0.0",
    sequence: 1,
    occurred_at: "2026-08-07T00:00:00Z",
    ...value,
  } as ChatStreamEvent;
}

describe("chat stream reducer", () => {
  it("assembles deltas and ignores replayed event IDs", () => {
    const delta = event({
      type: "response",
      event_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
      delta: "hello ",
    });
    const once = reduceChatStream(initialChatStreamState, delta);
    const replayed = reduceChatStream(once, delta);
    expect(once.text).toBe("hello ");
    expect(replayed).toBe(once);
  });

  it("tracks progress, typing, and safe errors", () => {
    const typing = reduceChatStream(
      initialChatStreamState,
      event({
        type: "typing",
        event_id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        active: true,
      }),
    );
    const progress = reduceChatStream(
      typing,
      event({
        type: "progress",
        event_id: "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
        stage: "planning",
        label: "Selected workflow",
      }),
    );
    const failed = reduceChatStream(
      progress,
      event({
        type: "error",
        event_id: "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
        error: {
          code: "EXECUTION_FAILED",
          message: "Safe failure",
          retryable: false,
          details: {},
        },
      }),
    );
    expect(progress.typing).toBe(true);
    expect(progress.progress).toEqual(["Selected workflow"]);
    expect(failed).toMatchObject({
      typing: false,
      status: "failed",
      error: "Safe failure",
    });
  });
});
