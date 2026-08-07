"use client";

import { Activity, Boxes, Command, Radio, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import type {
  CapabilityDescriptor,
  CommandDescriptor,
  CommandResponse,
  Health,
} from "@tradesentinel/contracts";
import {
  executeCommand,
  getCapabilities,
  getCommands,
  getHealth,
} from "@/lib/api";
import { ResponseComponentView } from "./response-component";

type LoadState = "loading" | "ready" | "error";

export function PlatformConsole() {
  const [state, setState] = useState<LoadState>("loading");
  const [health, setHealth] = useState<Health | null>(null);
  const [capabilities, setCapabilities] = useState<CapabilityDescriptor[]>([]);
  const [commands, setCommands] = useState<CommandDescriptor[]>([]);
  const [command, setCommand] = useState("/ping");
  const [result, setResult] = useState<CommandResponse | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([getHealth(), getCapabilities(), getCommands()])
      .then(([nextHealth, nextCapabilities, nextCommands]) => {
        setHealth(nextHealth);
        setCapabilities(nextCapabilities);
        setCommands(nextCommands);
        setState("ready");
      })
      .catch(() => setState("error"));
  }, []);

  async function runCommand(event: React.FormEvent) {
    event.preventDefault();
    setRunning(true);
    setError(null);
    try {
      setResult(await executeCommand(command));
    } catch {
      setError(
        "The command could not be completed. Check API readiness and try again.",
      );
    } finally {
      setRunning(false);
    }
  }

  return (
    <main>
      <header className="topbar">
        <a className="brand" href="#top" aria-label="TradeSentinel home">
          <span className="brand-mark">TS</span>
          <span>TradeSentinel</span>
        </a>
        <div className="environment">
          <span></span>Foundation environment
        </div>
      </header>
      <section className="hero" id="top">
        <div>
          <p className="eyebrow">Platform console · v0.1</p>
          <h1>
            Capability infrastructure,
            <br />
            <em>without hidden coupling.</em>
          </h1>
          <p className="lede">
            A live view of TradeSentinel’s domain-neutral runtime—registries,
            execution context, workflows, events, and dependency health.
          </p>
        </div>
        <div className="hero-orbit" aria-hidden="true">
          <span className="orbit orbit-one"></span>
          <span className="orbit orbit-two"></span>
          <div className="core">
            <ShieldCheck size={32} />
            <strong>CORE</strong>
            <small>domain agnostic</small>
          </div>
        </div>
      </section>
      {state === "loading" && (
        <section className="loading" aria-live="polite">
          Connecting to the platform…
        </section>
      )}
      {state === "error" && (
        <section className="error-panel" role="alert">
          <h2>Platform unavailable</h2>
          <p>The console is ready, but the API is not responding.</p>
        </section>
      )}
      {state === "ready" && (
        <>
          <section className="status-grid" aria-label="Platform status">
            <article>
              <Activity />
              <span>API status</span>
              <strong className={health?.status === "healthy" ? "good" : "bad"}>
                {health?.status}
              </strong>
              <small>
                Checked{" "}
                {health
                  ? new Date(health.checked_at).toLocaleTimeString()
                  : "—"}
              </small>
            </article>
            <article>
              <Boxes />
              <span>Capabilities</span>
              <strong>{capabilities.length.toString().padStart(2, "0")}</strong>
              <small>Validated at startup</small>
            </article>
            <article>
              <Command />
              <span>Commands</span>
              <strong>{commands.length.toString().padStart(2, "0")}</strong>
              <small>Collision protected</small>
            </article>
            <article>
              <Radio />
              <span>Event transport</span>
              <strong>READY</strong>
              <small>In-process or Redis Streams</small>
            </article>
          </section>
          <section className="workspace">
            <div className="command-panel">
              <div className="section-heading">
                <div>
                  <p className="eyebrow">Capability invocation</p>
                  <h2>Command console</h2>
                </div>
                <span className="kbd">⌘ K</span>
              </div>
              <form onSubmit={runCommand}>
                <label htmlFor="command">Registered command</label>
                <div className="command-input">
                  <span>›</span>
                  <input
                    id="command"
                    value={command}
                    onChange={(event) => setCommand(event.target.value)}
                    autoComplete="off"
                  />
                  <button disabled={running}>
                    {running ? "Running…" : "Execute"}
                  </button>
                </div>
              </form>
              {error && (
                <p className="form-error" role="alert">
                  {error}
                </p>
              )}
              {result ? (
                <div className="result-stack">
                  {result.response.components.map((component) => (
                    <ResponseComponentView
                      key={component.id}
                      value={component}
                    />
                  ))}
                </div>
              ) : (
                <div className="empty-result">
                  <div className="pulse-dot"></div>
                  <p>
                    Run <code>/ping</code> to trace a request through the
                    capability registry.
                  </p>
                </div>
              )}
            </div>
            <aside className="registry">
              <p className="eyebrow">Discovered registry</p>
              <h2>Installed surface</h2>
              <div className="registry-group">
                <h3>Capabilities</h3>
                {capabilities.map((item) => (
                  <div className="registry-item" key={item.name}>
                    <div>
                      <strong>{item.name}</strong>
                      <small>{item.description}</small>
                    </div>
                    <code>v{item.version}</code>
                  </div>
                ))}
              </div>
              <div className="registry-group">
                <h3>Commands</h3>
                {commands.map((item) => (
                  <div className="registry-item" key={item.name}>
                    <div>
                      <strong>{item.name}</strong>
                      <small>{item.target.name}</small>
                    </div>
                    <code>active</code>
                  </div>
                ))}
              </div>
            </aside>
          </section>
        </>
      )}
      <footer>
        <span>
          TRADE<span className="accent">SENTINEL</span>
        </span>
        <p>Foundation only · No market logic installed</p>
      </footer>
    </main>
  );
}
