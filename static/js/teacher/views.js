import { barChart } from "../charts.js";
import { el } from "../dom.js";
import { percent } from "../format.js";
import { ERROR_LABELS } from "../views.js";

const TASK_LABELS = {
  gap_fill: "пропуск",
  definition_match: "определение",
};

const CARD_FIELDS = [
  ["term", "Термин", "text"],
  ["transcription", "Транскрипция", "text"],
  ["part_of_speech", "Часть речи", "text"],
  ["definition_en", "Определение (English)", "area"],
  ["translation_ru", "Перевод на русский", "text"],
  ["collocations", "Словосочетания", "lines", "2-4 штуки, по одному в строке"],
  ["examples", "Примеры", "lines", "2-3 штуки, по одному в строке"],
  ["common_mistakes", "Типичные ошибки", "lines", "по одной в строке"],
  ["contrast_term", "Контрастный термин", "text"],
  ["domain", "Предметная область", "text"],
];

export function loginView({ name = "", error = "", onSubmit }) {
  const nameInput = el("input", { id: "name", type: "text", maxlength: 50, required: true, autocomplete: "username" });
  const passwordInput = el("input", { id: "password", type: "password", required: true, autocomplete: "current-password" });
  nameInput.value = name;
  return el(
    "form",
    {
      className: "card",
      onsubmit: (event) => {
        event.preventDefault();
        onSubmit(nameInput.value.trim(), passwordInput.value);
      },
    },
    el("h2", {}, "Вход преподавателя"),
    el("label", { for: "name" }, "Имя"),
    nameInput,
    el("label", { for: "password" }, "Пароль"),
    passwordInput,
    error && el("p", { className: "banner error", role: "alert" }, error),
    el("button", { type: "submit", className: "primary" }, "Войти"),
  );
}

export function tabsView(active, onSelect) {
  const tabs = [
    ["cards", "Карточки"],
    ["bank", "Банк заданий"],
    ["analytics", "Аналитика"],
  ];
  return el(
    "div",
    { className: "tabs", role: "tablist" },
    tabs.map(([id, label]) =>
      el("button", { type: "button", role: "tab", "aria-selected": String(id === active), onclick: () => onSelect(id) }, label),
    ),
  );
}

export function messageView(text) {
  return el("p", { className: "banner error", role: "alert" }, text);
}

function filterSelect(value, options, onChange) {
  const select = el("select", { "aria-label": "Фильтр" }, options.map(([id, label]) => el("option", { value: id }, label)));
  select.value = value;
  select.addEventListener("change", () => onChange(select.value));
  return select;
}

export function cardsView({ cards, filter, onFilter, onNew, onEdit, onVerify, onDelete }) {
  const rows = cards.map((card) =>
    el(
      "li",
      { className: "row" },
      el(
        "div",
        { className: "info" },
        el("strong", {}, card.term),
        " ",
        el("span", { className: "pos" }, card.part_of_speech),
        " ",
        el("span", { className: card.verified ? "badge ok" : "badge bad" }, card.verified ? "проверена" : "не проверена"),
        el("div", { className: "definition" }, card.definition_en),
      ),
      el(
        "div",
        { className: "buttons" },
        !card.verified && el("button", { type: "button", className: "primary", onclick: () => onVerify(card) }, "Проверено"),
        el("button", { type: "button", onclick: () => onEdit(card) }, "Изменить"),
        el("button", { type: "button", className: "danger", onclick: () => onDelete(card) }, "Удалить"),
      ),
    ),
  );
  return el(
    "section",
    { className: "card" },
    el(
      "div",
      { className: "toolbar" },
      filterSelect(filter, [["all", "Все карточки"], ["false", "Не проверены"], ["true", "Проверены"]], onFilter),
      el("button", { type: "button", className: "primary", onclick: onNew }, "Новая карточка"),
      el("span", { className: "meta" }, `Показано: ${cards.length}`),
    ),
    cards.length ? el("ul", { className: "list" }, rows) : el("p", {}, "Карточек нет."),
  );
}

export function cardFormView({ card, error = "", onSave, onCancel }) {
  const inputs = {};
  const fields = CARD_FIELDS.map(([name, label, kind, hint]) => {
    const input = el(kind === "text" ? "input" : "textarea", {
      id: `f-${name}`,
      type: kind === "text" ? "text" : null,
      rows: kind === "text" ? null : kind === "lines" ? 4 : 3,
    });
    const value = card ? card[name] : "";
    input.value = Array.isArray(value) ? value.join("\n") : value;
    inputs[name] = [input, kind];
    return el("div", { className: "field" }, el("label", { for: `f-${name}` }, label, hint && el("span", { className: "hint" }, ` (${hint})`)), input);
  });
  return el(
    "form",
    {
      className: "card",
      onsubmit: (event) => {
        event.preventDefault();
        const data = {};
        for (const [name, [input, kind]] of Object.entries(inputs)) {
          data[name] =
            kind === "lines"
              ? input.value.split("\n").map((line) => line.trim()).filter(Boolean)
              : input.value.trim();
        }
        onSave(data);
      },
    },
    el("h2", {}, card ? `Изменить: ${card.term}` : "Новая карточка"),
    card && el("p", { className: "meta" }, "После сохранения карточку нужно проверить заново."),
    fields,
    error && el("p", { className: "banner error", role: "alert" }, error),
    el("div", { className: "actions" }, el("button", { type: "submit", className: "primary" }, "Сохранить"), el("button", { type: "button", className: "secondary", onclick: onCancel }, "Отмена")),
  );
}

export function bankView({ entries, filter, onFilter, onToggle }) {
  const rows = entries.map((entry) =>
    el(
      "li",
      { className: entry.rejected ? "row rejected" : "row" },
      el(
        "div",
        { className: "info" },
        el("strong", {}, entry.term),
        " ",
        el("span", { className: "badge" }, TASK_LABELS[entry.task_type] || entry.task_type),
        " ",
        el("span", { className: "meta" }, `${entry.source}, показано: ${entry.times_used}`),
        entry.rejected && el("span", { className: "badge bad" }, "убрано"),
        el("p", {}, entry.prompt),
        el(
          "ul",
          { className: "bank-options" },
          entry.options.map((option) =>
            el("li", { className: option === entry.correct_answer ? "correct" : "" }, option === entry.correct_answer ? `${option} (верный)` : option),
          ),
        ),
      ),
      el(
        "div",
        { className: "buttons" },
        el(
          "button",
          { type: "button", className: entry.rejected ? "" : "danger", onclick: () => onToggle(entry) },
          entry.rejected ? "Вернуть в банк" : "Убрать из банка",
        ),
      ),
    ),
  );
  return el(
    "section",
    { className: "card" },
    el(
      "div",
      { className: "toolbar" },
      filterSelect(filter, [["all", "Все задания"], ["false", "Используются"], ["true", "Убранные"]], onFilter),
      el("span", { className: "meta" }, `Показано: ${entries.length}`),
    ),
    entries.length ? el("ul", { className: "list" }, rows) : el("p", {}, "В банке пока нет заданий. Они появляются, когда студенты проходят сессии."),
  );
}

export function analyticsView({ data, minAnswers, onMinAnswers }) {
  const minInput = el("input", { id: "min-answers", type: "number", min: 1, max: 100, value: minAnswers });
  minInput.addEventListener("change", () => onMinAnswers(Math.max(1, Number(minInput.value) || 1)));
  const sources = { task: "по типу задания", rule: "правилами", llm: "моделью" };

  const typeRows = data.error_types.map((item) => ({
    label: ERROR_LABELS[item.error_type],
    value: item.share,
    text: `${item.count} (${percent(item.share)})`,
  }));
  const termRows = data.hardest_terms.map((item) => ({
    label: item.term,
    value: item.error_rate,
    text: `${item.errors} из ${item.attempts} (${percent(item.error_rate)})`,
  }));

  return el(
    "section",
    { className: "card" },
    el(
      "div",
      { className: "summary" },
      el("div", {}, el("strong", {}, String(data.students)), "студентов"),
      el("div", {}, el("strong", {}, String(data.answers)), "ответов"),
      el("div", {}, el("strong", {}, percent(data.error_rate)), "доля ошибок"),
    ),
    el(
      "p",
      { className: "meta" },
      `Считаются первые ответы на задания в сессии, повторы после ошибки не входят. Данные по группе, без имен. Тренировочные ответы (${data.practice_answers}) не входят в расчет: тренировка добровольная и не влияет на расписание.`,
    ),
    el("h3", {}, "Распределение ошибок по типам"),
    data.errors ? barChart("Распределение ошибок по типам", typeRows) : el("p", {}, "Ошибок пока нет."),
    el("h3", {}, "Термины с наибольшей долей ошибок"),
    el("div", { className: "toolbar" }, el("label", { for: "min-answers" }, "Минимум ответов на термин:"), minInput),
    termRows.length ? barChart("Термины с наибольшей долей ошибок", termRows) : el("p", {}, "Нет терминов с ошибками при таком пороге."),
    el(
      "p",
      { className: "meta" },
      `Как определены ошибки и ответы: ${data.classified_by.map((item) => `${sources[item.classified_by] || item.classified_by} - ${item.count}`).join(", ") || "данных нет"}.`,
    ),
  );
}
