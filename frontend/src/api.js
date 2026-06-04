export async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }

  return response.status === 204 ? null : response.json();
}

export function listSessions(userId) {
  return api(`/sessions?user_id=${encodeURIComponent(userId)}`);
}

export function createSession(userId, title) {
  return api("/sessions", {
    method: "POST",
    body: JSON.stringify({ user_id: userId, title: title || null }),
  });
}

export function getSession(sessionId) {
  return api(`/sessions/${encodeURIComponent(sessionId)}`);
}

export function updateSession(sessionId, payload) {
  return api(`/sessions/${encodeURIComponent(sessionId)}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function deleteSession(sessionId) {
  return api(`/sessions/${encodeURIComponent(sessionId)}`, {
    method: "DELETE",
  });
}

export function sendChatMessage({ userId, sessionId, message }) {
  return api("/chat", {
    method: "POST",
    body: JSON.stringify({
      user_id: userId,
      session_id: sessionId,
      message,
    }),
  });
}
