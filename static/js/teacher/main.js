import { createApi } from "../api.js";
import { clear, el } from "../dom.js";
import * as views from "./views.js";

const api = createApi();
const ROLES = ["teacher", "admin"];
const root = document.getElementById("app");
const userBox = document.getElementById("user-box");

const state = { tab: "cards", cardFilter: "all", bankFilter: "all", minAnswers: 3, personalOwner: "" };
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
  api.logout();
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
          const me = await api.login(value, { password });
          if (!ROLES.includes(me.role)) {
            await api.logout();
            showLogin(value, "Этот кабинет только для преподавателей. Студентам - главная страница приложения.");
            return;
          }
          renderUserBox();
          showShell();
        } catch (err) {
          showLogin(value, err.message);
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
  if (state.tab === "decks") {
    return guarded(showDecks);
  }
  if (state.tab === "personal") {
    return guarded(showPersonal);
  }
  if (state.tab === "bank") {
    return guarded(showBank);
  }
  return guarded(showAnalytics);
}

async function showCards() {
  const query = state.cardFilter === "all" ? "" : `?verified=${state.cardFilter}`;
  const cards = await api.request(`/admin/cards${query}`);
  show(
    views.cardsView({
      cards,
      filter: state.cardFilter,
      onFilter: (value) => {
        state.cardFilter = value;
        guarded(showCards);
      },
      onNew: () => guarded(() => showCardForm(null)),
      onEdit: (card) => guarded(() => showCardForm(card)),
      onVerify: (card) => guarded(async () => {
        await api.request(`/admin/cards/${card.id}/verify`, { method: "PATCH" });
        await showCards();
      }),
      onDelete: (card) => {
        const text = `Удалить карточку «${card.term}»? Вместе с ней удалятся прогресс студентов, история ответов и задания из банка.`;
        if (window.confirm(text)) {
          guarded(async () => {
            await api.request(`/admin/cards/${card.id}`, { method: "DELETE" });
            await showCards();
          });
        }
      },
    }),
  );
}

async function showCardForm(card, error = "", draft = card) {
  const domains = await api.request("/domains");
  show(
    views.cardFormView({
      card: draft,
      domains,
      error,
      onCancel: () => guarded(showCards),
      onSave: async (data) => {
        try {
          if (card) {
            await api.request(`/admin/cards/${card.id}`, { method: "PUT", body: data });
          } else {
            await api.request("/admin/cards", { method: "POST", body: data });
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
  const entries = await api.request(`/admin/bank${query}`);
  show(
    views.bankView({
      entries,
      filter: state.bankFilter,
      onFilter: (value) => {
        state.bankFilter = value;
        guarded(showBank);
      },
      onToggle: (entry) => guarded(async () => {
        await api.request(`/admin/bank/${entry.id}`, { method: "PATCH", body: { rejected: !entry.rejected } });
        await showBank();
      }),
    }),
  );
}

async function showAnalytics() {
  const data = await api.request(`/admin/analytics?min_answers=${state.minAnswers}`);
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
  try {
    const me = await api.me();
    if (!ROLES.includes(me.role)) {
      logout();
      return;
    }
  } catch (error) {
    if (error.status === 401) {
      showLogin();
      return;
    }
  }
  renderUserBox();
  showShell();
}

init();

async function showDecks(notice = "", error = "") {
  const [decks, domains] = await Promise.all([api.request("/admin/decks"), api.request("/domains")]);
  show(
    views.decksView({
      decks,
      domains,
      notice,
      error,
      onNew: () => guarded(() => showDeckForm(null)),
      onEdit: (deck) => guarded(() => showDeckForm(deck)),
      onCards: (deck) => guarded(() => showDeckCards(deck)),
      onDelete: (deck) => {
        if (window.confirm(`Удалить набор «${deck.name}»? Карточки останутся, но выбор этого набора у студентов пропадет.`)) {
          guarded(async () => {
            await api.request(`/admin/decks/${deck.id}`, { method: "DELETE" });
            await showDecks("Набор удален.");
          });
        }
      },
      onNewDomain: (name) => guarded(async () => {
        if (!name) {
          return showDecks("", "Введите название области.");
        }
        try {
          await api.request("/admin/domains", { method: "POST", body: { name } });
          return showDecks(`Область «${name}» добавлена.`);
        } catch (err) {
          if (err.status === 409) {
            return showDecks("", "Такая область уже есть.");
          }
          throw err;
        }
      }),
    }),
  );
}

async function showDeckForm(deck, error = "", draft = deck) {
  const domains = await api.request("/domains");
  show(
    views.deckFormView({
      deck: draft,
      domains,
      error,
      onCancel: () => guarded(() => showDecks()),
      onSave: async (data) => {
        try {
          if (deck) {
            await api.request(`/admin/decks/${deck.id}`, { method: "PUT", body: data });
          } else {
            await api.request("/admin/decks", { method: "POST", body: data });
          }
          await showDecks("Набор сохранен.");
        } catch (err) {
          if (err.status === 401 || err.status === 403) {
            logout("Сессия истекла или нет прав преподавателя, войдите снова.");
            return;
          }
          showDeckForm(deck, err.message, { ...(deck || {}), ...data });
        }
      },
    }),
  );
}

async function showDeckCards(deck) {
  const cards = await api.request("/admin/cards");
  show(
    views.deckCardsView({
      deck,
      cards,
      onBack: () => guarded(() => showDecks()),
      onSave: (ids) => guarded(async () => {
        await api.request(`/admin/decks/${deck.id}/cards`, { method: "PUT", body: { card_ids: ids } });
        await showDecks(`Состав набора «${deck.name}» сохранен: ${ids.length}.`);
      }),
    }),
  );
}

async function showPersonal() {
  const query = state.personalOwner ? `?owner=${encodeURIComponent(state.personalOwner)}` : "";
  const [cards, all] = await Promise.all([api.request(`/admin/personal-cards${query}`), api.request("/admin/personal-cards")]);
  show(
    views.personalView({
      cards,
      owners: [...new Set(all.map((card) => card.owner))].sort(),
      owner: state.personalOwner,
      onOwner: (value) => {
        state.personalOwner = value;
        guarded(showPersonal);
      },
      onOpen: (card) => guarded(() => showPersonalCard(card)),
    }),
  );
}

async function showPersonalCard(card, extra = {}) {
  const [decks, domains] = await Promise.all([api.request("/admin/decks"), api.request("/domains")]);
  show(
    views.personalCardView({
      card,
      decks,
      domains,
      ...extra,
      onBack: () => guarded(showPersonal),
      onSave: async (data) => {
        try {
          const saved = await api.request(`/admin/personal-cards/${card.id}`, { method: "PUT", body: data });
          showPersonalCard(saved, { notice: "Изменения сохранены." });
        } catch (err) {
          if (err.status === 401 || err.status === 403) {
            logout("Сессия истекла или нет прав преподавателя, войдите снова.");
            return;
          }
          showPersonalCard({ ...card, ...data }, { error: err.message });
        }
      },
      onPromote: async (deckIds) => {
        try {
          await api.request(`/admin/personal-cards/${card.id}/promote`, { method: "POST", body: { deck_ids: deckIds } });
          state.tab = "personal";
          await showPersonal();
        } catch (err) {
          if (err.status === 401 || err.status === 403) {
            logout("Сессия истекла или нет прав преподавателя, войдите снова.");
            return;
          }
          showPersonalCard(card, { error: err.message });
        }
      },
    }),
  );
}
