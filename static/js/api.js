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

export function createApi() {
  let name = null;

  const getName = () => name;

  async function request(path, { method = "GET", body } = {}) {
    const headers = {};
    if (body) {
      headers["Content-Type"] = "application/json";
    }

    let response;
    try {
      response = await fetch(path, {
        method,
        headers,
        credentials: "same-origin",
        body: body ? JSON.stringify(body) : undefined,
      });
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

  async function authenticate(path, body) {
    const data = await request(path, { method: "POST", body });
    name = data.name;
    return data;
  }

  const login = (loginName, extra = {}) => authenticate("/auth/login", { name: loginName, ...extra });
  const register = (registerName, password, passwordConfirm, role) =>
    authenticate("/auth/register", { name: registerName, password, password_confirm: passwordConfirm, role });

  async function me() {
    const data = await request("/auth/me");
    name = data.name;
    return data;
  }

  async function logout() {
    name = null;
    try {
      await request("/auth/logout", { method: "POST" });
    } catch {
      // сессия на сервере истечет сама, если он недоступен
    }
  }

  return { getName, request, login, register, me, logout };
}

const student = createApi();

export const { getName, login, register, me, logout } = student;
export const progress = () => student.request("/me/progress");
export const history = (query) => student.request(`/me/history${query}`);
export const dictionary = () => student.request("/me/dictionary");
export const stats = () => student.request("/me/stats");
export const practiceNext = (exclude) => student.request(`/practice/next${exclude ? `?exclude=${exclude}` : ""}`);
export const practiceAnswer = (payload) => student.request("/practice/answer", { method: "POST", body: payload });
export const settings = () => student.request("/me/settings");
export const saveSettings = (value) => student.request("/me/settings", { method: "PUT", body: { new_cards_per_day: value } });
export const decks = () => student.request("/me/decks");
export const saveDecks = (ids) => student.request("/me/decks", { method: "PUT", body: { deck_ids: ids } });
export const domains = () => student.request("/domains");
export const drafts = () => student.request("/me/drafts");
export const createDraft = (term, domain) => student.request("/me/drafts", { method: "POST", body: { term, domain } });
export const updateDraft = (id, body) => student.request(`/me/drafts/${id}`, { method: "PUT", body });
export const confirmDraft = (id, body) => student.request(`/me/drafts/${id}/confirm`, { method: "POST", body });
export const deleteDraft = (id) => student.request(`/me/drafts/${id}`, { method: "DELETE" });
export const myCards = () => student.request("/me/cards");
export const updateMyCard = (id, body) => student.request(`/me/cards/${id}`, { method: "PUT", body });
export const deleteMyCard = (id) => student.request(`/me/cards/${id}`, { method: "DELETE" });
export const limits = () => student.request("/me/limits");
export const extract = (text, domain) => student.request("/me/extract", { method: "POST", body: { text, domain } });
export const nextTask = () => student.request("/session/next");
export const answer = (payload) => student.request("/session/answer", { method: "POST", body: payload });
