"use client";

import { KeyRound, LockKeyhole } from "lucide-react";
import { useState } from "react";

export function TokenGate({
  title,
  children,
}: {
  title: string;
  children: (token: string) => React.ReactNode;
}) {
  const [token, setToken] = useState("");
  const [unlocked, setUnlocked] = useState(false);
  if (!unlocked)
    return (
      <section className="token-gate">
        <LockKeyhole size={30} />
        <span className="eyebrow">Restricted operator surface</span>
        <h1>{title}</h1>
        <p>The token is kept in React memory only and is never persisted.</p>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            if (token) setUnlocked(true);
          }}
        >
          <label htmlFor="admin-token">Administrative token</label>
          <input
            id="admin-token"
            type="password"
            value={token}
            onChange={(event) => setToken(event.target.value)}
            autoComplete="off"
          />
          <button type="submit" disabled={!token}>
            <KeyRound size={16} />
            Unlock this tab
          </button>
        </form>
      </section>
    );
  return <>{children(token)}</>;
}
