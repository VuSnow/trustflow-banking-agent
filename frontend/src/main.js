import { h, render } from "https://esm.sh/preact@10.24.3";
import { useEffect, useMemo, useRef, useState } from "https://esm.sh/preact@10.24.3/hooks";
import { marked } from "https://esm.sh/marked@15.0.7";
import createDOMPurify from "https://esm.sh/dompurify@3.1.6";
import {
  Archive,
  Bot,
  Check,
  MessageSquarePlus,
  RefreshCw,
  Send,
  Trash2,
  UserRound,
} from "https://esm.sh/lucide-preact@0.468.0";
import {
  createSession,
  deleteSession,
  getSession,
  listSessions,
  sendChatMessage,
  updateSession,
} from "./api.js";
import { formatDate, previewTitle } from "./utils.js";

const e = h;
const DOMPurify = createDOMPurify(window);

marked.setOptions({
  breaks: true,
  gfm: true,
});

function renderMarkdown(value) {
  const html = marked.parse(value || "", { async: false });
  return DOMPurify.sanitize(html);
}

function IconButton({ title, onClick, children, kind = "ghost", disabled = false }) {
  return e(
    "button",
    { class: `icon-button ${kind}`, title, "aria-label": title, onClick, disabled },
    children,
  );
}

function Sidebar({ userId, setUserId, sessions, activeId, onRefresh, onCreate, onOpen }) {
  return e(
    "aside",
    { class: "sidebar" },
    e("div", { class: "brand" }, e("h1", null, "TrustFlow"), e("p", null, "Banking assistant sessions")),
    e(
      "div",
      { class: "user-strip" },
      e(UserRound, { size: 18 }),
      e("input", {
        value: userId,
        onInput: (event) => setUserId(event.currentTarget.value),
        placeholder: "user id",
      }),
    ),
    e(
      "div",
      { class: "toolbar" },
      e(IconButton, { title: "New session", kind: "primary", onClick: onCreate }, e(MessageSquarePlus, { size: 18 })),
      e(IconButton, { title: "Refresh sessions", onClick: onRefresh }, e(RefreshCw, { size: 18 })),
    ),
    e("div", { class: "sidebar-count" }, `${sessions.length} session${sessions.length === 1 ? "" : "s"}`),
    e(
      "div",
      { class: "session-list" },
      sessions.map((session) =>
        e(
          "button",
          {
            key: session.session_id,
            class: `session-row ${session.session_id === activeId ? "active" : ""}`,
            onClick: () => onOpen(session.session_id),
          },
          e("span", { class: "session-title" }, previewTitle(session)),
          e("span", { class: "session-subtitle" }, `${session.message_count || 0} messages`),
          e("span", { class: "session-subtitle" }, formatDate(session.updated_at)),
        ),
      ),
    ),
  );
}

function Topbar({ session, title, setTitle, onRename, onDelete }) {
  return e(
    "header",
    { class: "topbar" },
    e(
      "div",
      { class: "session-heading" },
      e("h2", null, session ? previewTitle(session) : "Select a session"),
      e(
        "p",
        null,
        session
          ? `${session.session_id} | ${session.message_count || 0} messages | ${formatDate(session.updated_at)}`
          : "Create or choose a session to begin.",
      ),
    ),
    e(
      "div",
      { class: "title-tools" },
      e("input", {
        value: title,
        onInput: (event) => setTitle(event.currentTarget.value),
        placeholder: "Session title",
        disabled: !session,
      }),
      e(IconButton, { title: "Save title", onClick: () => onRename(), disabled: !session }, e(Check, { size: 18 })),
      e(IconButton, { title: "Archive session", onClick: () => onRename("archived"), disabled: !session }, e(Archive, { size: 18 })),
      e(IconButton, { title: "Delete session", kind: "danger", onClick: onDelete, disabled: !session }, e(Trash2, { size: 18 })),
    ),
  );
}

function MessageBubble({ message }) {
  const isUser = message.role === "user";
  const payload = message.data ? JSON.stringify(message.data, null, 2) : null;
  return e(
    "article",
    { class: `message ${isUser ? "user" : "assistant"}` },
    e(
      "div",
      { class: "message-meta" },
      e("span", null, isUser ? "You" : "TrustFlow"),
      e("span", null, formatDate(message.created_at)),
    ),
    e("div", {
      class: "message-text",
      dangerouslySetInnerHTML: { __html: renderMarkdown(message.message) },
    }),
    payload ? e("details", null, e("summary", null, "Response data"), e("pre", null, payload)) : null,
  );
}

function MessageList({ messages, activeSessionId }) {
  const ref = useRef(null);
  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [messages.length, activeSessionId]);

  return e(
    "section",
    { class: "messages", ref },
    !activeSessionId
      ? e("div", { class: "empty-state" }, e(Bot, { size: 34 }), e("h3", null, "No session selected"))
      : messages.length === 0
        ? e("div", { class: "empty-state" }, e(Bot, { size: 34 }), e("h3", null, "Start the conversation"))
        : messages.map((message) => e(MessageBubble, { key: message.id || `${message.role}-${message.created_at}`, message })),
  );
}

function Composer({ disabled, onSend }) {
  const [value, setValue] = useState("");

  async function submit() {
    const message = value.trim();
    if (!message) return;
    setValue("");
    await onSend(message);
  }

  return e(
    "footer",
    { class: "composer" },
    e("textarea", {
      value,
      disabled,
      placeholder: disabled ? "Create or select a session first" : "Ask TrustFlow...",
      onInput: (event) => setValue(event.currentTarget.value),
      onKeyDown: (event) => {
        if (event.key === "Enter" && !event.shiftKey) {
          event.preventDefault();
          submit();
        }
      },
    }),
    e(IconButton, { title: "Send", kind: "primary", disabled, onClick: submit }, e(Send, { size: 18 })),
  );
}

function App() {
  const [userId, setUserId] = useState("u1");
  const [sessions, setSessions] = useState([]);
  const [activeSessionId, setActiveSessionId] = useState(null);
  const [activeSession, setActiveSession] = useState(null);
  const [messages, setMessages] = useState([]);
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const canSend = useMemo(() => Boolean(activeSessionId && !busy), [activeSessionId, busy]);

  async function refreshSessions() {
    if (!userId.trim()) return;
    setError("");
    const data = await listSessions(userId.trim());
    setSessions(data);
  }

  async function openSession(sessionId) {
    setError("");
    const detail = await getSession(sessionId);
    setActiveSessionId(detail.session_id);
    setActiveSession(detail);
    setMessages(detail.messages || []);
    setTitle(detail.title || "");
  }

  async function handleCreate() {
    setBusy(true);
    try {
      const session = await createSession(userId.trim(), title.trim() || null);
      await refreshSessions();
      await openSession(session.session_id);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleRename(status) {
    if (!activeSessionId) return;
    setBusy(true);
    try {
      const payload = { title: title.trim() || activeSession?.title || activeSessionId };
      if (status) payload.status = status;
      const session = await updateSession(activeSessionId, payload);
      setActiveSession(session);
      await refreshSessions();
      await openSession(session.session_id);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete() {
    if (!activeSessionId || !confirm("Delete this session and all messages?")) return;
    setBusy(true);
    try {
      await deleteSession(activeSessionId);
      setActiveSessionId(null);
      setActiveSession(null);
      setMessages([]);
      setTitle("");
      await refreshSessions();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleSend(message) {
    if (!activeSessionId) return;
    setBusy(true);
    try {
      await sendChatMessage({ userId: userId.trim(), sessionId: activeSessionId, message });
      await refreshSessions();
      await openSession(activeSessionId);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    refreshSessions().catch((err) => setError(err.message));
  }, [userId]);

  return e(
    "main",
    { class: "app-shell" },
    e(Sidebar, {
      userId,
      setUserId,
      sessions,
      activeId: activeSessionId,
      onRefresh: refreshSessions,
      onCreate: handleCreate,
      onOpen: openSession,
    }),
    e(
      "section",
      { class: "workspace" },
      e(Topbar, {
        session: activeSession,
        title,
        setTitle,
        onRename: handleRename,
        onDelete: handleDelete,
      }),
      error ? e("div", { class: "error-banner" }, error) : null,
      e(MessageList, { messages, activeSessionId }),
      e(Composer, { disabled: !canSend, onSend: handleSend }),
    ),
  );
}

render(e(App), document.getElementById("app"));
