export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

async function request(method, path, body) {
  let response;
  try {
    response = await fetch(path, {
      method,
      headers: body === undefined ? {} : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError("Сервер недоступен. Проверьте, что приложение запущено.", 0);
  }

  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(errorMessage(data, response.status), response.status);
  }
  return data;
}

function errorMessage(data, status) {
  const detail = data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length) return detail.map((item) => item.msg).join("; ");
  return `Ошибка запроса (${status}).`;
}

export const api = {
  getState: () => request("GET", "/api/v1/me/state"),
  getMessages: () => request("GET", "/api/v1/me/messages"),
  getExercises: () => request("GET", "/api/v1/exercises"),
  sendMessage: (message, useRag) => request("POST", "/api/v1/chat/messages", { message, use_rag: useRag }),
  setExerciseStatus: (id, status) => request("PATCH", `/api/v1/exercises/${encodeURIComponent(id)}`, { status }),
  deleteExercise: (id) => request("DELETE", `/api/v1/exercises/${encodeURIComponent(id)}`),
  checkReadiness: () => request("POST", "/api/v1/me/readiness"),
  reset: () => request("POST", "/api/v1/me/reset"),
};
