import { createApi } from "../api.js";
import { confirmDialog, icon, promptDialog, toast } from "../components.js";
import { clear, el } from "../dom.js";
import { themeToggle } from "../theme.js";
import * as studentViews from "./students-views.js";
import * as views from "./views.js";

const api = createApi();
const ROLES = ["teacher", "admin"];
const root = document.getElementById("app");
const userBox = document.getElementById("user-box");

const state = { tab: "cards", groupId: null, cardFilter: "all", bankFilter: "all", minAnswers: 3, personalOwner: "" };
let content = null;
let role = "admin";

const scope = () => (role === "admin" ? "/admin" : "/teacher");

function enter(me) {
  role = me.role;
  state.tab = role === "admin" ? "cards" : "students";
}

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
  userBox.append(themeToggle());
  const name = api.getName();
  if (name) {
    userBox.append(
      el("span", { className: "user-name" }, name),
      el("a", { href: "/" }, "Для студента"),
      el("button", { type: "button", className: "icon-button", "aria-label": "Выйти", title: "Выйти", onclick: () => logout() }, icon("log-out", 20)),
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
          enter(me);
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
      views.tabsView(
        state.tab,
        (id) => {
          state.tab = id;
          renderTabs();
          openTab();
        },
        role === "admin" ? views.ADMIN_TABS : views.TEACHER_TABS,
      ),
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
  if (state.tab === "students") {
    return guarded(() => showStudents());
  }
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
  const query = role === "admin" && state.cardFilter !== "all" ? `?verified=${state.cardFilter}` : "";
  const cards = await api.request(`${scope()}/cards${query}`);
  show(
    views.cardsView({
      cards,
      filter: state.cardFilter,
      onFilter: role === "admin" ? (value) => {
        state.cardFilter = value;
        guarded(showCards);
      } : null,
      onNew: () => guarded(() => showCardForm(null)),
      onEdit: (card) => guarded(() => showCardForm(card)),
      onVerify: (card) => guarded(async () => {
        await api.request(`/admin/cards/${card.id}/verify`, { method: "PATCH" });
        await showCards();
      }),
      onDelete: async (card) => {
        const text = `Удалить карточку «${card.term}»? Вместе с ней удалятся прогресс студентов, история ответов и задания из банка.`;
        if (await confirmDialog(text, { title: "Удалить карточку", confirmText: "Удалить", danger: true })) {
          guarded(async () => {
            await api.request(`${scope()}/cards/${card.id}`, { method: "DELETE" });
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
            await api.request(`${scope()}/cards/${card.id}`, { method: "PUT", body: data });
          } else {
            await api.request(`${scope()}/cards`, { method: "POST", body: data });
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
  const group = role === "teacher" && state.groupId ? `&group_id=${state.groupId}` : "";
  const data = await api.request(`${scope()}/analytics?min_answers=${state.minAnswers}${group}`);
  const groups = role === "teacher" ? await api.request("/teacher/groups") : [];
  show(
    views.analyticsView({
      data,
      groupFilter: role === "teacher"
        ? studentViews.groupFilterView(groups, state.groupId, (id) => {
            state.groupId = id;
            guarded(showAnalytics);
          })
        : null,
      minAnswers: state.minAnswers,
      onMinAnswers: (value) => {
        state.minAnswers = value;
        guarded(showAnalytics);
      },
    }),
  );
}

async function init() {
  let me = null;
  try {
    me = await api.me();
  } catch (error) {
    renderUserBox();
    showLogin("", error.status === 401 ? "" : error.message);
    return;
  }
  if (!ROLES.includes(me.role)) {
    logout();
    return;
  }
  enter(me);
  renderUserBox();
  showShell();
}

init();

async function showDecks(notice = "", error = "") {
  const [decks, domains] = await Promise.all([api.request(`${scope()}/decks`), api.request("/domains")]);
  show(
    views.decksView({
      decks,
      domains,
      notice,
      error,
      onNew: () => guarded(() => showDeckForm(null)),
      onEdit: (deck) => guarded(() => showDeckForm(deck)),
      onCards: (deck) => guarded(() => showDeckCards(deck)),
      onGroups: role === "teacher" ? (deck) => guarded(() => showDeckGroups(deck)) : null,
      onDelete: async (deck) => {
        if (await confirmDialog(`Удалить набор «${deck.name}»? Карточки останутся, но выбор этого набора у студентов пропадет.`, { title: "Удалить набор", confirmText: "Удалить", danger: true })) {
          guarded(async () => {
            await api.request(`${scope()}/decks/${deck.id}`, { method: "DELETE" });
            await showDecks("Набор удален.");
          });
        }
      },
      onNewDomain: role !== "admin" ? null : (name) => guarded(async () => {
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
            await api.request(`${scope()}/decks/${deck.id}`, { method: "PUT", body: data });
          } else {
            await api.request(`${scope()}/decks`, { method: "POST", body: data });
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
  const cards = await api.request(`${scope()}/cards`);
  show(
    views.deckCardsView({
      deck,
      cards,
      onBack: () => guarded(() => showDecks()),
      onSave: (ids) => guarded(async () => {
        await api.request(`${scope()}/decks/${deck.id}/cards`, { method: "PUT", body: { card_ids: ids } });
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

async function showDeckGroups(deck) {
  const groups = await api.request("/teacher/groups");
  show(
    studentViews.deckGroupsView({
      deck,
      groups,
      onBack: () => guarded(() => showDecks()),
      onSave: (ids) => guarded(async () => {
        await api.request(`/teacher/decks/${deck.id}/groups`, { method: "PUT", body: { group_ids: ids } });
        await showDecks(`Назначение набора «${deck.name}» сохранено: групп ${ids.length}.`);
      }),
    }),
  );
}

async function showStudents(notice = "", error = "") {
  const [data, groups, links] = await Promise.all([
    api.request("/teacher/students"),
    api.request("/teacher/groups"),
    api.request("/teacher/links"),
  ]);
  const act = (work, message) => guarded(async () => {
    try {
      await work();
      toast(message);
      await showStudents();
    } catch (err) {
      if (err.status === 401 || err.status === 403) {
        throw err;
      }
      await showStudents("", err.message);
    }
  });
  show(
    studentViews.studentsView({
      data,
      groups,
      links,
      notice,
      error,
      handlers: {
        onInvite: (name, groupId) => {
          if (!name) {
            return showStudents("", "Введите ник студента.");
          }
          return act(
            () => api.request("/teacher/invitations", { method: "POST", body: { name, group_id: groupId } }),
            "Если такой студент есть, ему отправлено приглашение.",
          );
        },
        onAccept: (request, groupId) => act(
          () => api.request(`/teacher/requests/${request.id}/accept`, { method: "POST", body: { group_id: groupId } }),
          `Студент ${request.name} добавлен.`,
        ),
        onDecline: (request) => act(() => api.request(`/teacher/requests/${request.id}/decline`, { method: "POST" }), "Заявка отклонена."),
        onCancel: (invitation) => act(() => api.request(`/teacher/invitations/${invitation.id}`, { method: "DELETE" }), "Приглашение отменено."),
        onNewGroup: (name) => {
          if (!name) {
            return showStudents("", "Введите название группы.");
          }
          return act(() => api.request("/teacher/groups", { method: "POST", body: { name } }), `Группа «${name}» создана.`);
        },
        onRename: async (group) => {
          const name = await promptDialog("Новое название группы", group.name);
          if (name && name.trim() && name.trim() !== group.name) {
            act(() => api.request(`/teacher/groups/${group.id}`, { method: "PUT", body: { name: name.trim() } }), "Группа переименована.");
          }
        },
        onDeleteGroup: async (group) => {
          if (await confirmDialog(`Удалить группу «${group.name}»? Студенты останутся, но будут без группы, а назначенные группе наборы перестанут быть доступны.`, { title: "Удалить группу", confirmText: "Удалить", danger: true })) {
            act(() => api.request(`/teacher/groups/${group.id}`, { method: "DELETE" }), "Группа удалена.");
          }
        },
        onMove: (student, groupId) => act(
          () => api.request(`/teacher/students/${encodeURIComponent(student.name)}/group`, { method: "PUT", body: { group_id: groupId } }),
          `Студент ${student.name} перемещен.`,
        ),
        onRemove: async (student) => {
          if (await confirmDialog(`Убрать студента ${student.name}? Вы перестанете видеть его данные.`, { title: "Убрать студента", confirmText: "Убрать", danger: true })) {
            act(() => api.request(`/teacher/students/${encodeURIComponent(student.name)}`, { method: "DELETE" }), "Студент убран.");
          }
        },
      },
    }),
  );
}
