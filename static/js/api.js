export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

function describe(detail, status) {
  if (typeof detail === "string") {
    return detail;
  }
  if (Array.isArray(detail)) {
    return detail.map((item) => `${(item.loc || []).slice(1).join(".")}: ${item.msg}`).join("; ");
  }
  return `Ошибка ${status}`;
}

export function createApi(prefix) {
  const tokenKey = `${prefix}_token`;
  const nameKey = `${prefix}_name`;

  const read = (key) => {
    try {
      return localStorage.getItem(key);
    } catch {
      return null;
    }
  };

  const write = (key, value) => {
    try {
      if (value) {
        localStorage.setItem(key, value);
      } else {
        localStorage.removeItem(key);
      }
    } catch {
      // localStorage может быть недоступен (приватный режим): работаем без сохранения
    }
  };

  const getToken = () => read(tokenKey);
  const getName = () => read(nameKey);

  function clearSession() {
    write(tokenKey, null);
    write(nameKey, null);
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
      let detail = null;
      try {
        detail = (await response.json()).detail;
      } catch {
        // тело ответа не JSON, остается общее сообщение
      }
      throw new ApiError(response.status, describe(detail, response.status));
    }
    return response.status === 204 ? null : response.json();
  }

  async function login(name, extra = {}) {
    const data = await request("/auth/login", { method: "POST", body: { name, ...extra } });
    write(tokenKey, data.token);
    write(nameKey, data.name);
    return data;
  }

  return { getToken, getName, clearSession, request, login };
}

const student = createApi("vt");

export const { getToken, getName, clearSession, login } = student;
export const me = () => student.request("/auth/me");
export const nextTask = () => student.request("/session/next");
export const answer = (payload) => student.request("/session/answer", { method: "POST", body: payload });
