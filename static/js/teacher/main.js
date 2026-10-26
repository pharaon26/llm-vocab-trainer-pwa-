import { createApi } from "../api.js";
import { clear, el } from "../dom.js";
import * as views from "./views.js";

const api = createApi("vt_teacher");
const root = document.getElementById("app");
const userBox = document.getElementById("user-box");

const state = { tab: "cards", cardFilter: "all", bankFilter: "all", minAnswers: 3 };
let content = null;

function showPage(node) {
  clear(root);
  root.append(node);
  const heading = root.querySelector("h2");
  if (heading) {
    heading.tabIndex = -1;
    heading.focus({ preventScroll: true });
  }
}

function renderUserBox() {
  clear(userBox);
  const name = api.getName();
  if (name) {
    userBox.append(
      el("span", {}, name),
      " ",
      el("a", { href: "/" }, "Приложение студента"),
      " ",
      el("button", { type: "button", className: "link", onclick: () => logout() }, "Выйти"),
    );
  }
}

function logout(message = "") {
  api.clearSession();
  renderUserBox();
  showLogin("", message);
}

function showLogin(name = "", error = "") {
  showPage(
    views.loginView({
      name,
      error,
      onSubmit: async (value, password) => {
        try {
          await api.login(value, { role: "teacher", password });
          renderUserBox();
          showShell();
        } catch (err) {
          const hint = err.status === 403 ? "Неверный пароль или вход преподавателя отключен (не задан TEACHER_PASSWORD)." : err.message;
          showLogin(value, hint);
        }
      },
    }),
  );
}

function showShell() {
  const tabs = el("div", {});
  content = el("div", {});
  const renderTabs = () => {
    tabs.replaceChildren(
      views.tabsView(state.tab, (id) => {
        state.tab = id;
        renderTabs();
        openTab();
      }),
    );
  };
  renderTabs();
  showPage(el("div", {}, tabs, content));
  openTab();
}

function show(node) {
  clear(content);
  content.append(node);
}

async function guarded(action) {
  try {
    await action();
  } catch (error) {
    if (error.status === 401 || error.status === 403) {
      logout("Сессия истекла или нет прав преподавателя, войдите снова.");
      return;
    }
    show(views.messageView(error.message));
  }
}

function openTab() {
  if (state.tab === "cards") {
    return guarded(showCards);
  }
  if (state.tab === "bank") {
    return guarded(showBank);
  }
  return guarded(showAnalytics);
}

async function showCards() {
  const query = state.cardFilter === "all" ? "" : `?verified=${state.cardFilter}`;
  const cards = await api.request(`/cards${query}`);
  show(
    views.cardsView({
      cards,
      filter: state.cardFilter,
      onFilter: (value) => {
        state.cardFilter = value;
        guarded(showCards);
      },
      onNew: () => showCardForm(null),
      onEdit: (card) => showCardForm(card),
      onVerify: (card) => guarded(async () => {
        await api.request(`/cards/${card.id}/verify`, { method: "PATCH" });
        await showCards();
      }),
      onDelete: (card) => {
        const text = `Удалить карточку «${card.term}»? Вместе с ней удалятся прогресс студентов, история ответов и задания из банка.`;
        if (window.confirm(text)) {
          guarded(async () => {
            await api.request(`/cards/${card.id}`, { method: "DELETE" });
            await showCards();
          });
        }
      },
    }),
  );
}

function showCardForm(card, error = "", draft = card) {
  show(
    views.cardFormView({
      card: draft,
      error,
      onCancel: () => guarded(showCards),
      onSave: async (data) => {
        try {
          if (card) {
            await api.request(`/cards/${card.id}`, { method: "PUT", body: data });
          } else {
            await api.request("/cards", { method: "POST", body: data });
          }
          await showCards();
        } catch (err) {
          if (err.status === 401 || err.status === 403) {
            logout("Сессия истекла или нет прав преподавателя, войдите снова.");
            return;
          }
          showCardForm(card, err.message, { ...(card || {}), ...data });
        }
      },
    }),
  );
}

async function showBank() {
  const query = state.bankFilter === "all" ? "" : `?rejected=${state.bankFilter}`;
  const entries = await api.request(`/teacher/bank${query}`);
  show(
    views.bankView({
      entries,
      filter: state.bankFilter,
      onFilter: (value) => {
        state.bankFilter = value;
        guarded(showBank);
      },
      onToggle: (entry) => guarded(async () => {
        await api.request(`/teacher/bank/${entry.id}`, { method: "PATCH", body: { rejected: !entry.rejected } });
        await showBank();
      }),
    }),
  );
}

async function showAnalytics() {
  const data = await api.request(`/teacher/analytics?min_answers=${state.minAnswers}`);
  show(
    views.analyticsView({
      data,
      minAnswers: state.minAnswers,
      onMinAnswers: (value) => {
        state.minAnswers = value;
        guarded(showAnalytics);
      },
    }),
  );
}

async function init() {
  renderUserBox();
  if (!api.getToken()) {
    showLogin();
    return;
  }
  try {
    const me = await api.request("/auth/me");
    if (me.role !== "teacher") {
      logout();
      return;
    }
  } catch (error) {
    if (error.status === 401) {
      logout();
      return;
    }
  }
  showShell();
}

init();
