"use client";

import {
  Archive,
  Bot,
  CheckCircle2,
  ChevronDown,
  Menu,
  MessageSquare,
  Pencil,
  Plus,
  Send,
  User,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type {
  ChatMessage,
  ChatSession,
  ChatSessionDetail,
  CommandDescriptor,
} from "@tradesentinel/contracts";
import {
  createSession,
  getCommands,
  getHealth,
  getSession,
  listSessions,
  sendMessage,
  subscribeToTurn,
  updateSession,
} from "@/lib/api";
import {
  initialChatStreamState,
  reduceChatStream,
  type ChatStreamState,
} from "@/lib/chat-state";
import { ResponseComponentView } from "./response-component";

type LoadState = "loading" | "ready" | "error";

export function PlatformConsole() {
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [detail, setDetail] = useState<ChatSessionDetail | null>(null);
  const [commands, setCommands] = useState<CommandDescriptor[]>([]);
  const [composer, setComposer] = useState("");
  const [stream, setStream] = useState<ChatStreamState>(initialChatStreamState);
  const [sending, setSending] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [showArchived, setShowArchived] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const streamCleanup = useRef<(() => void) | null>(null);
  const transcriptEnd = useRef<HTMLDivElement | null>(null);

  const refreshSessions = useCallback(
    async (archived = showArchived) => {
      const page = await listSessions(archived);
      setSessions(page.items);
    },
    [showArchived],
  );

  const openSession = useCallback(async (id: string) => {
    streamCleanup.current?.();
    streamCleanup.current = null;
    const next = await getSession(id);
    setDetail(next);
    setStream(initialChatStreamState);
    setError(null);
    window.history.replaceState(null, "", `/?session=${id}`);
    setSidebarOpen(false);
    if (next.active_turn) {
      streamCleanup.current = subscribeToTurn(
        `/api/v1/chat/turns/${next.active_turn.id}/events`,
        {
          event: (event) =>
            setStream((current) => reduceChatStream(current, event)),
          reconnecting: () =>
            setStream((current) => ({ ...current, reconnecting: true })),
        },
      );
    }
  }, []);

  useEffect(() => {
    void Promise.all([getHealth(), getCommands(), listSessions(false)])
      .then(async ([, nextCommands, page]) => {
        setCommands(nextCommands);
        setSessions(page.items);
        const requested = new URLSearchParams(window.location.search).get(
          "session",
        );
        const initial = requested ?? page.items[0]?.id;
        if (initial) await openSession(initial);
        setLoadState("ready");
      })
      .catch(() => setLoadState("error"));
    return () => streamCleanup.current?.();
  }, [openSession]);

  useEffect(() => {
    transcriptEnd.current?.scrollIntoView({ behavior: "smooth" });
  }, [detail?.messages, stream.text, stream.typing]);

  const currentSessionId = detail?.session.id;

  useEffect(() => {
    if (!stream.completedMessage || !currentSessionId) return;
    void Promise.all([
      getSession(currentSessionId),
      refreshSessions(false),
    ]).then(([next]) => {
      setDetail(next);
      setSending(false);
      setStream(initialChatStreamState);
    });
  }, [stream.completedMessage, currentSessionId, refreshSessions]);

  const commandMatches = useMemo(() => {
    if (!composer.startsWith("/") || composer.includes(" ")) return [];
    return commands.filter((command) => command.name.startsWith(composer));
  }, [commands, composer]);

  async function newChat() {
    try {
      const session = await createSession();
      await refreshSessions(false);
      await openSession(session.id);
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Could not create chat.",
      );
    }
  }

  async function submit() {
    const message = composer.trim();
    if (!message || sending) return;
    setComposer("");
    setSending(true);
    setError(null);
    setStream(initialChatStreamState);
    const clientMessageId = crypto.randomUUID();
    const optimistic: ChatMessage = {
      id: clientMessageId,
      session_id: detail?.session.id ?? clientMessageId,
      turn_id: clientMessageId,
      role: "user",
      content: message,
      status: "completed",
      created_at: new Date().toISOString(),
      completed_at: new Date().toISOString(),
    };
    if (detail) {
      setDetail({ ...detail, messages: [...detail.messages, optimistic] });
    }
    try {
      const accepted = await sendMessage({
        message,
        sessionId: detail?.session.id,
        clientMessageId,
      });
      if (!detail || detail.session.id !== accepted.session_id) {
        await openSession(accepted.session_id);
      }
      await refreshSessions(false);
      streamCleanup.current?.();
      streamCleanup.current = subscribeToTurn(accepted.stream_url, {
        event: (event) =>
          setStream((current) => reduceChatStream(current, event)),
        reconnecting: () =>
          setStream((current) => ({ ...current, reconnecting: true })),
      });
    } catch (cause) {
      setSending(false);
      setError(cause instanceof Error ? cause.message : "Message failed.");
    }
  }

  async function renameCurrent() {
    if (!detail) return;
    const title = window.prompt("Rename chat", detail.session.title)?.trim();
    if (!title) return;
    const session = await updateSession(detail.session.id, { title });
    setDetail({ ...detail, session });
    await refreshSessions();
  }

  async function archiveCurrent() {
    if (!detail || detail.active_turn) return;
    await updateSession(detail.session.id, { archived: true });
    setDetail(null);
    window.history.replaceState(null, "", "/");
    await refreshSessions(false);
  }

  async function toggleArchived() {
    const next = !showArchived;
    setShowArchived(next);
    const page = await listSessions(next);
    setSessions(page.items);
    setDetail(null);
  }

  if (loadState === "loading") {
    return <div className="app-loading">Connecting to TradeSentinel…</div>;
  }
  if (loadState === "error") {
    return (
      <div className="app-loading error" role="alert">
        The chat service is unavailable. Check API readiness and reload.
      </div>
    );
  }

  return (
    <main className="chat-shell">
      <aside className={`sidebar ${sidebarOpen ? "open" : ""}`}>
        <div className="sidebar-brand">
          <div className="brand-mark">TS</div>
          <strong>TradeSentinel</strong>
          <button
            className="icon-button mobile-only"
            onClick={() => setSidebarOpen(false)}
            aria-label="Close sidebar"
          >
            <X size={18} />
          </button>
        </div>
        <button className="new-chat" onClick={() => void newChat()}>
          <Plus size={17} /> New chat
        </button>
        <div className="history-label">
          <span>{showArchived ? "Archived" : "Recent chats"}</span>
        </div>
        <nav className="session-list" aria-label="Chat history">
          {sessions.map((session) => (
            <button
              key={session.id}
              className={detail?.session.id === session.id ? "active" : ""}
              onClick={() => void openSession(session.id)}
            >
              <MessageSquare size={15} />
              <span>{session.title}</span>
            </button>
          ))}
          {!sessions.length && (
            <p className="empty-history">
              No {showArchived ? "archived" : "saved"} chats.
            </p>
          )}
        </nav>
        <button
          className="archive-toggle"
          onClick={() => void toggleArchived()}
        >
          <Archive size={16} />
          {showArchived ? "Back to active chats" : "Archived chats"}
        </button>
        <div className="runtime-note">
          <span></span>
          Mock runtime · no market features
        </div>
      </aside>

      {sidebarOpen && (
        <button className="scrim" onClick={() => setSidebarOpen(false)} />
      )}

      <section className="chat-main">
        <header className="chat-header">
          <button
            className="icon-button mobile-only"
            onClick={() => setSidebarOpen(true)}
            aria-label="Open sidebar"
          >
            <Menu size={20} />
          </button>
          <div>
            <strong>{detail?.session.title ?? "TradeSentinel Chat"}</strong>
            <small>Deterministic capability runtime</small>
          </div>
          {detail && (
            <div className="header-actions">
              <button
                className="icon-button"
                onClick={() => void renameCurrent()}
                aria-label="Rename chat"
              >
                <Pencil size={17} />
              </button>
              <button
                className="icon-button"
                onClick={() => void archiveCurrent()}
                disabled={Boolean(detail.active_turn)}
                aria-label="Archive chat"
              >
                <Archive size={17} />
              </button>
            </div>
          )}
        </header>

        <div className="transcript" aria-live="polite">
          {!detail?.messages.length && !sending ? (
            <div className="welcome">
              <div className="assistant-logo">
                <Bot size={30} />
              </div>
              <h1>How can I help you test TradeSentinel?</h1>
              <p>
                This chat uses deterministic mock capabilities. It does not
                perform market research or call an LLM.
              </p>
              <div className="prompt-grid">
                {["Explain this mock runtime", "/ping", "/echo hello"].map(
                  (prompt) => (
                    <button key={prompt} onClick={() => setComposer(prompt)}>
                      <strong>{prompt}</strong>
                      <span>Try the capability pipeline</span>
                    </button>
                  ),
                )}
              </div>
            </div>
          ) : (
            <div className="message-list">
              {detail?.messages.map((message) => (
                <Message key={message.id} message={message} />
              ))}
              {(sending || stream.text || stream.error) && (
                <div className="message assistant-message">
                  <div className="avatar assistant">
                    <Bot size={17} />
                  </div>
                  <div className="message-body">
                    <div className="execution-line">
                      {stream.reconnecting
                        ? "Reconnecting"
                        : stream.status === "idle"
                          ? "Queued"
                          : stream.status}
                      {stream.typing && (
                        <span className="typing-dots">
                          <i></i>
                          <i></i>
                          <i></i>
                        </span>
                      )}
                    </div>
                    {stream.progress.length > 0 && (
                      <details
                        className="progress"
                        open={stream.status !== "completed"}
                      >
                        <summary>
                          Execution progress <ChevronDown size={14} />
                        </summary>
                        {stream.progress.map((item) => (
                          <div key={item}>
                            <CheckCircle2 size={14} /> {item}
                          </div>
                        ))}
                      </details>
                    )}
                    {stream.text && (
                      <p className="streamed-text">{stream.text}</p>
                    )}
                    {stream.error && (
                      <p className="message-error" role="alert">
                        {stream.error}
                      </p>
                    )}
                    {stream.warnings.map((warning) => (
                      <p className="warning" key={warning}>
                        {warning}
                      </p>
                    ))}
                    {stream.components.map((component) => (
                      <ResponseComponentView
                        key={component.id}
                        value={component}
                      />
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
          <div ref={transcriptEnd} />
        </div>

        <div className="composer-wrap">
          {error && (
            <p className="composer-error" role="alert">
              {error}
            </p>
          )}
          {commandMatches.length > 0 && (
            <div
              className="command-menu"
              role="listbox"
              aria-label="Slash commands"
            >
              {commandMatches.map((command) => (
                <button
                  key={command.name}
                  onClick={() => setComposer(`${command.name} `)}
                >
                  <code>{command.name}</code>
                  <span>{command.description}</span>
                  <small>{command.examples[0]}</small>
                </button>
              ))}
            </div>
          )}
          <div className="composer">
            <textarea
              value={composer}
              onChange={(event) => setComposer(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void submit();
                }
              }}
              placeholder="Message TradeSentinel or type / for commands"
              rows={1}
              disabled={sending}
              aria-label="Chat message"
            />
            <button
              className="send-button"
              onClick={() => void submit()}
              disabled={!composer.trim() || sending}
              aria-label="Send message"
            >
              <Send size={18} />
            </button>
          </div>
          <small className="disclaimer">
            Mock infrastructure only. No financial analysis is installed.
          </small>
        </div>
      </section>
    </main>
  );
}

function Message({ message }: { message: ChatMessage }) {
  return (
    <article
      className={`message ${message.role === "user" ? "user-message" : "assistant-message"}`}
    >
      <div className={`avatar ${message.role}`}>
        {message.role === "user" ? <User size={17} /> : <Bot size={17} />}
      </div>
      <div className="message-body">
        <p className="message-author">
          {message.role === "user" ? "You" : "TradeSentinel"}
        </p>
        <p className="message-content">{message.content}</p>
        {message.error && (
          <p className="message-error">{message.error.message}</p>
        )}
        {message.response?.components.map((component) => (
          <ResponseComponentView key={component.id} value={component} />
        ))}
      </div>
    </article>
  );
}
