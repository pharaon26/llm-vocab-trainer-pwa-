import * as api from "./api.js";
import { confirmDialog, toast } from "./components.js";
import { el } from "./dom.js";
import { loadingView } from "./views.js";
import { show, unauthorized } from "./ui.js";

function pendingList(items, empty, buttons) {
  if (!items.length) {
    return el("p", { className: "meta" }, empty);
  }
  return el(
    "ul",
    { className: "list" },
    items.map((item) => el("li", { className: "row" }, el("div", { className: "info" }, el("strong", {}, item.name)), el("div", { className: "buttons" }, buttons(item)))),
  );
}

function teachersView({ data, notice, error, onAsk, onAccept, onDecline, onCancel, onLeave }) {
  const nick = el("input", { id: "teacher-name", type: "text", maxlength: 50, placeholder: "ник преподавателя", autocomplete: "off", "aria-label": "Ник преподавателя" });
  return el(
    "section",
    { className: "card" },
    el("h2", {}, "Мои преподаватели"),
    notice && el("p", { className: "banner ok", role: "status" }, notice),
    error && el("p", { className: "banner error", role: "alert" }, error),
    el("h3", {}, `Приглашения (${data.invitations.length})`),
    pendingList(data.invitations, "Приглашений нет.", (item) => [
      el("button", { type: "button", className: "primary", onclick: () => onAccept(item) }, "Принять"),
      el("button", { type: "button", onclick: () => onDecline(item) }, "Отклонить"),
    ]),
    el("h3", {}, "Подать заявку преподавателю"),
    el(
      "div",
      { className: "toolbar" },
      nick,
      el("button", { type: "button", className: "primary", onclick: () => onAsk(nick.value.trim()) }, "Отправить заявку"),
    ),
    el("p", { className: "meta" }, "Преподаватель увидит вашу заявку и решит, принять ее или нет. Пока он не принял, он ничего о вас не видит."),
    el("h3", {}, `Отправленные заявки (${data.requests.length})`),
    pendingList(data.requests, "Ожидающих заявок нет.", (item) => [el("button", { type: "button", onclick: () => onCancel(item) }, "Отменить")]),
    el("h3", {}, `Мои преподаватели (${data.teachers.length})`),
    pendingList(data.teachers, "Вы пока не учитесь ни у кого.", (item) => [el("button", { type: "button", className: "danger", onclick: () => onLeave(item) }, "Отвязаться")]),
    data.teachers.length ? el("p", { className: "meta" }, "Преподаватель видит сводку (сколько терминов выучено, точность, дата последнего занятия) и общую аналитику ошибок. Отдельные ответы и ваши личные карточки он не видит. После «Отвязаться» доступ пропадает сразу.") : null,
  );
}

export async function showTeachers(notice = "", error = "") {
  show(loadingView("Загружаем преподавателей…"));
  try {
    const data = await api.myTeachers();
    const act = async (work, message) => {
      try {
        await work();
        toast(message);
        await showTeachers();
      } catch (err) {
        if (err.status === 401) {
          unauthorized();
        } else {
          await showTeachers("", err.message);
        }
      }
    };
    show(
      teachersView({
        data,
        notice,
        error,
        onAsk: (name) => (name ? act(() => api.requestTeacher(name), "Если такой преподаватель есть, ему отправлена заявка.") : showTeachers("", "Введите ник преподавателя.")),
        onAccept: (item) => act(() => api.answerInvitation(item.id, true), `Вы теперь учитесь у ${item.name}.`),
        onDecline: (item) => act(() => api.answerInvitation(item.id, false), "Приглашение отклонено."),
        onCancel: (item) => act(() => api.cancelRequest(item.id), "Заявка отменена."),
        onLeave: async (item) => {
          if (await confirmDialog(`Отвязаться от преподавателя ${item.name}? Его наборы перестанут быть вам доступны.`, { title: "Разорвать связь", confirmText: "Отвязаться", danger: true })) {
            act(() => api.leaveTeacher(item.name), "Связь разорвана.");
          }
        },
      }),
    );
  } catch (err) {
    if (err.status === 401) {
      unauthorized();
    } else {
      show(el("p", { className: "banner error", role: "alert" }, err.message));
    }
  }
}
