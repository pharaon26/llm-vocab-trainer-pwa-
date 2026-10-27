import { el } from "../dom.js";
import { percent } from "../format.js";

function groupSelect(groups, value = "", { none = "Без группы" } = {}) {
  const select = el(
    "select",
    { "aria-label": "Группа" },
    el("option", { value: "" }, none),
    groups.map((group) => el("option", { value: String(group.id) }, group.name)),
  );
  select.value = value === null ? "" : String(value);
  return select;
}

const groupId = (select) => (select.value ? Number(select.value) : null);

function studentRow(student, groups, current, { onMove, onRemove }) {
  const move = groupSelect(groups, current);
  move.addEventListener("change", () => onMove(student, groupId(move)));
  const stats = student.answered
    ? `выучено: ${student.learned}, точность: ${percent(student.accuracy)}, ответов: ${student.answered}`
    : `выучено: ${student.learned}, ответов пока нет`;
  return el(
    "li",
    { className: "row" },
    el(
      "div",
      { className: "info" },
      el("strong", {}, student.name),
      el("div", { className: "meta" }, `${stats}; последнее занятие: ${student.last_active || "не было"}`),
    ),
    el("div", { className: "buttons" }, move, el("button", { type: "button", className: "danger", onclick: () => onRemove(student) }, "Убрать")),
  );
}

export function studentsView({ data, groups, links, notice = "", error = "", handlers }) {
  const nick = el("input", {
    id: "invite-name", type: "text", maxlength: 50, placeholder: "ник студента", autocomplete: "off",
    "aria-label": "Ник студента",
  });
  const inviteGroup = groupSelect(groups);
  const newGroup = el("input", { id: "new-group", type: "text", maxlength: 100, placeholder: "Название группы", "aria-label": "Новая группа" });

  const requests = links.requests.map((request) => {
    const select = groupSelect(groups);
    return el(
      "li",
      { className: "row" },
      el("div", { className: "info" }, el("strong", {}, request.name), el("div", { className: "meta" }, "хочет учиться у вас")),
      el(
        "div",
        { className: "buttons" },
        select,
        el("button", { type: "button", className: "primary", onclick: () => handlers.onAccept(request, groupId(select)) }, "Принять"),
        el("button", { type: "button", onclick: () => handlers.onDecline(request) }, "Отклонить"),
      ),
    );
  });
  const invitations = links.invitations.map((invitation) =>
    el(
      "li",
      { className: "row" },
      el("div", { className: "info" }, el("strong", {}, invitation.name), el("div", { className: "meta" }, "ждет ответа")),
      el("div", { className: "buttons" }, el("button", { type: "button", onclick: () => handlers.onCancel(invitation) }, "Отменить")),
    ),
  );
  const sections = data.groups.map((group) => {
    const named = group.id !== null;
    return el(
      "div",
      {},
      el(
        "div",
        { className: "toolbar" },
        el("h4", {}, named ? group.name : "Без группы"),
        named && el("button", { type: "button", onclick: () => handlers.onRename(group) }, "Переименовать"),
        named && el("button", { type: "button", className: "danger", onclick: () => handlers.onDeleteGroup(group) }, "Удалить группу"),
      ),
      group.students.length
        ? el("ul", { className: "list" }, group.students.map((student) => studentRow(student, groups, group.id, handlers)))
        : el("p", { className: "meta" }, "В группе пока никого нет."),
    );
  });
  const known = new Set(data.groups.map((group) => group.id));
  const emptyGroups = groups.filter((group) => !known.has(group.id));

  return el(
    "section",
    { className: "card" },
    notice && el("p", { className: "banner ok", role: "status" }, notice),
    error && el("p", { className: "banner error", role: "alert" }, error),
    el("h3", {}, "Пригласить студента"),
    el(
      "div",
      { className: "toolbar" },
      nick,
      inviteGroup,
      el("button", { type: "button", className: "primary", onclick: () => handlers.onInvite(nick.value.trim(), groupId(inviteGroup)) }, "Пригласить"),
    ),
    el("p", { className: "meta" }, "Студент увидит приглашение у себя в разделе «Преподаватели». Связь появится, когда он его примет."),
    el("h3", {}, `Заявки студентов (${links.requests.length})`),
    requests.length ? el("ul", { className: "list" }, requests) : el("p", { className: "meta" }, "Новых заявок нет."),
    el("h3", {}, `Отправленные приглашения (${links.invitations.length})`),
    invitations.length ? el("ul", { className: "list" }, invitations) : el("p", { className: "meta" }, "Ожидающих приглашений нет."),
    el("h3", {}, "Мои студенты и группы"),
    el(
      "div",
      { className: "toolbar" },
      newGroup,
      el("button", { type: "button", onclick: () => handlers.onNewGroup(newGroup.value.trim()) }, "Создать группу"),
    ),
    data.groups.length ? sections : el("p", {}, "Студентов пока нет."),
    emptyGroups.map((group) =>
      el(
        "div",
        {},
        el(
          "div",
          { className: "toolbar" },
          el("h4", {}, group.name),
          el("button", { type: "button", onclick: () => handlers.onRename(group) }, "Переименовать"),
          el("button", { type: "button", className: "danger", onclick: () => handlers.onDeleteGroup(group) }, "Удалить группу"),
        ),
        el("p", { className: "meta" }, "В группе пока никого нет."),
      ),
    ),
  );
}

export function deckGroupsView({ deck, groups, onSave, onBack }) {
  const boxes = groups.map((group) => {
    const box = el("input", { type: "checkbox", id: `group-${group.id}`, value: String(group.id) });
    box.checked = deck.group_ids.includes(group.id);
    return box;
  });
  return el(
    "section",
    { className: "card" },
    el("h3", {}, `Набор «${deck.name}»: кому назначить`),
    el("p", { className: "meta" }, "Карточки набора появятся у студентов выбранных групп и будут входить в их новые термины."),
    groups.length
      ? el("ul", { className: "list" }, groups.map((group, index) => el("li", {}, el("label", { className: "check", for: `group-${group.id}` }, boxes[index], ` ${group.name} (студентов: ${group.students})`))))
      : el("p", {}, "Сначала создайте группы в разделе «Мои студенты»."),
    el(
      "div",
      { className: "toolbar" },
      el("button", { type: "button", className: "primary", onclick: () => onSave(boxes.filter((box) => box.checked).map((box) => Number(box.value))) }, "Сохранить"),
      el("button", { type: "button", onclick: onBack }, "Назад"),
    ),
  );
}

export function groupFilterView(groups, value, onChange) {
  const select = groupSelect(groups, value, { none: "Все студенты" });
  select.addEventListener("change", () => onChange(groupId(select)));
  return el("div", { className: "toolbar" }, el("label", {}, "Группа: "), select);
}
