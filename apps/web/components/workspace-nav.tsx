import {
  Bot,
  ChartNoAxesCombined,
  MessageSquare,
  Settings,
} from "lucide-react";
import Link from "next/link";

export function WorkspaceNav({
  current,
}: {
  current: "chat" | "workspace" | "admin";
}) {
  return (
    <nav className="workspace-nav" aria-label="Primary navigation">
      <Link href="/" className="nav-brand">
        <span>TS</span>
        <strong>TradeSentinel</strong>
      </Link>
      <div>
        <Link href="/" aria-current={current === "chat" ? "page" : undefined}>
          <MessageSquare size={16} /> Chat
        </Link>
        <Link
          href="/workspace"
          aria-current={current === "workspace" ? "page" : undefined}
        >
          <ChartNoAxesCombined size={16} /> Workspace
        </Link>
        <Link
          href="/admin"
          aria-current={current === "admin" ? "page" : undefined}
        >
          <Settings size={16} /> Admin
        </Link>
      </div>
      <span className="nav-runtime">
        <Bot size={14} /> Evidence-first runtime
      </span>
    </nav>
  );
}
