import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import type { AgentStep, ChatReply } from "./api";
import { useAuth } from "./auth";

export interface Turn {
  role: "user" | "assistant";
  content: string;
  steps?: AgentStep[];
}

interface ChatValue {
  turns: Turn[];
  busy: boolean;
  error: string;
  send: (text: string) => Promise<void>;
  reset: () => void;
}

const ChatContext = createContext<ChatValue | null>(null);
const key = (email: string) => `opspilot.chat.${email}`;

function load(email: string): Turn[] {
  try {
    const raw = sessionStorage.getItem(key(email));
    return raw ? (JSON.parse(raw) as Turn[]) : [];
  } catch {
    return [];
  }
}

function store(email: string, turns: Turn[]) {
  try {
    if (turns.length) sessionStorage.setItem(key(email), JSON.stringify(turns));
    else sessionStorage.removeItem(key(email));
  } catch {
    /* storage unavailable: the conversation lives in memory only */
  }
}

/**
 * Holds the Copilot conversation above the routes, so it survives navigating
 * between pages, and saves it per user for the browser tab, so it survives
 * reloads and switching accounts. A reply that arrives after the user has
 * left the Copilot page is still kept.
 */
export function ChatProvider({ children }: { children: ReactNode }) {
  const { call, session } = useAuth();
  const email = session?.email ?? "";
  const [turns, setTurns] = useState<Turn[]>(() => (email ? load(email) : []));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const owner = useRef(email);

  // Switching accounts swaps in that account's conversation.
  useEffect(() => {
    owner.current = email;
    setTurns(email ? load(email) : []);
    setBusy(false);
    setError("");
  }, [email]);

  const send = useCallback(
    async (text: string) => {
      const content = text.trim();
      if (!content || busy || !email) return;
      const forUser = email;
      const history = [...turns, { role: "user" as const, content }];
      setTurns(history);
      store(forUser, history);
      setBusy(true);
      setError("");
      try {
        const r = await call<ChatReply>("/chat", {
          method: "POST",
          body: JSON.stringify({ messages: history.map(({ role, content }) => ({ role, content })) }),
        });
        const next = [...history, { role: "assistant" as const, content: r.reply, steps: r.steps }];
        store(forUser, next);
        if (owner.current === forUser) setTurns(next);
      } catch (e) {
        if (owner.current === forUser) setError(e instanceof Error ? e.message : "The agent did not respond");
      } finally {
        if (owner.current === forUser) setBusy(false);
      }
    },
    [busy, call, email, turns],
  );

  const reset = useCallback(() => {
    setTurns([]);
    setError("");
    if (email) store(email, []);
  }, [email]);

  const value = useMemo(() => ({ turns, busy, error, send, reset }), [turns, busy, error, send, reset]);
  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>;
}

export function useChat() {
  const ctx = useContext(ChatContext);
  if (!ctx) throw new Error("useChat outside ChatProvider");
  return ctx;
}
