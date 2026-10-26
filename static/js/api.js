const TOKEN_KEY = "vt_token";
const NAME_KEY = "vt_name";

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

function read(key) {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key, value) {
  try {
    if (value) {
      localStorage.setItem(key, value);
    } else {
      localStorage.removeItem(key);
    }
  } catch {
    // localStorage может быть недоступен (приватный режим): работаем без сохранения
  }
}

export const getToken = () => read(TOKEN_KEY);
export const getName = () => read(NAME_KEY);

export function clearSession() {
  write(TOKEN_KEY, null);
  write(NAME_KEY, null);
}

async function request(path, { method = "GET", body } = {}) {
  const headers = {};
  if (body) {
    headers["Content-Type"] = "application/json";
  }
  const token = getToken();
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  let response;
  try {
    response = await fetch(path, { method, headers, body: body ? JSON.stringify(body) : undefined });
  } catch {
    throw new ApiError(0, "Нет соединения с сервером");
  }

  if (!response.ok) {
    let detail = `Ошибка ${response.status}`;
    try {
      const data = await response.json();
      if (typeof data.detail === "string") {
        detail = data.detail;
      }
    } catch {
      // тело ответа не JSON, остается общее сообщение
    }
    throw new ApiError(response.status, detail);
  }
  return response.status === 204 ? null : response.json();
}

export async function login(name) {
  const data = await request("/auth/login", { method: "POST", body: { name } });
  write(TOKEN_KEY, data.token);
  write(NAME_KEY, data.name);
  return data;
}

export const me = () => request("/auth/me");
export const nextTask = () => request("/session/next");
export const answer = (payload) => request("/session/answer", { method: "POST", body: payload });
