import { barChart } from "../charts.js";
import { el } from "../dom.js";
import { percent } from "../format.js";
import { SOURCE_CLASS, SOURCE_LABELS } from "../page-views.js";
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
  ["contrast_term", "Контрастный термин", "text", "необязательно"],
  ["domain", "Предметная область", "domain"],
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
    ["decks", "Наборы"],
    ["personal", "Личные карточки"],
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

export function cardFormView({ card, domains = [], error = "", onSave, onCancel }) {
  const inputs = {};
  const fields = CARD_FIELDS.map(([name, label, kind, hint]) => {
    const single = kind === "text" || kind === "domain";
    const input = el(single ? "input" : "textarea", {
      id: `f-${name}`,
      type: single ? "text" : null,
      list: kind === "domain" ? "domain-list" : null,
      rows: single ? null : kind === "lines" ? 4 : 3,
    });
    const value = card ? card[name] : "";
    input.value = Array.isArray(value) ? value.join("\n") : value;
    inputs[name] = [input, kind];
    return el(
      "div",
      { className: "field" },
      el("label", { for: `f-${name}` }, label, hint && el("span", { className: "hint" }, ` (${hint})`)),
      input,
      kind === "domain" && el("datalist", { id: "domain-list" }, domains.map((item) => el("option", { value: item.name }))),
    );
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
        if (!data.contrast_term) {
          data.contrast_term = null;
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

export function decksView({ decks, domains, onNew, onEdit, onDelete, onCards, onNewDomain, notice = "", error = "" }) {
  const domainInput = el("input", { id: "new-domain-name", type: "text", maxlength: 50, placeholder: "Новая область, например Aviation" });
  const rows = decks.map((deck) =>
    el(
      "li",
      { className: "row" },
      el(
        "div",
        { className: "info" },
        el("strong", {}, deck.name),
        " ",
        el("span", { className: "badge" }, deck.domain),
        deck.is_default && el("span", { className: "badge ok" }, "по умолчанию"),
        el("div", { className: "definition" }, deck.description || "Без описания"),
        el("div", { className: "meta" }, `Карточек: ${deck.cards_total}, проверенных: ${deck.cards}`),
      ),
      el(
        "div",
        { className: "buttons" },
        el("button", { type: "button", onclick: () => onCards(deck) }, "Состав"),
        el("button", { type: "button", onclick: () => onEdit(deck) }, "Изменить"),
        el("button", { type: "button", className: "danger", onclick: () => onDelete(deck) }, "Удалить"),
      ),
    ),
  );
  return el(
    "section",
    { className: "card" },
    el("div", { className: "toolbar" }, el("button", { type: "button", className: "primary", onclick: onNew }, "Новый набор")),
    notice && el("p", { className: "banner ok", role: "status" }, notice),
    error && el("p", { className: "banner error", role: "alert" }, error),
    decks.length ? el("ul", { className: "list" }, rows) : el("p", {}, "Наборов нет."),
    el("h3", {}, "Области"),
    el("p", { className: "meta" }, domains.map((item) => item.name).join(", ")),
    el(
      "div",
      { className: "toolbar" },
      domainInput,
      el("button", { type: "button", onclick: () => onNewDomain(domainInput.value.trim()) }, "Добавить область"),
    ),
  );
}

export function deckFormView({ deck, domains, error = "", onSave, onCancel }) {
  const name = el("input", { id: "d-name", type: "text", maxlength: 100, required: true });
  const description = el("textarea", { id: "d-description", rows: 3 });
  const domain = el("input", { id: "d-domain", type: "text", maxlength: 50, required: true, list: "d-domain-list" });
  const isDefault = el("input", { id: "d-default", type: "checkbox" });
  name.value = deck?.name ?? "";
  description.value = deck?.description ?? "";
  domain.value = deck?.domain ?? "";
  isDefault.checked = deck?.is_default ?? false;
  return el(
    "form",
    {
      className: "card",
      onsubmit: (event) => {
        event.preventDefault();
        onSave({ name: name.value.trim(), description: description.value.trim(), domain: domain.value.trim(), is_default: isDefault.checked });
      },
    },
    el("h2", {}, deck ? `Изменить набор: ${deck.name}` : "Новый набор"),
    el("div", { className: "field" }, el("label", { for: "d-name" }, "Название"), name),
    el("div", { className: "field" }, el("label", { for: "d-description" }, "Описание"), description),
    el(
      "div",
      { className: "field" },
      el("label", { for: "d-domain" }, "Область"),
      domain,
      el("datalist", { id: "d-domain-list" }, domains.map((item) => el("option", { value: item.name }))),
    ),
    el("label", { className: "deck-option", for: "d-default" }, isDefault, el("span", {}, "Выбран по умолчанию у новых студентов и у тех, кто еще не менял выбор наборов")),
    error && el("p", { className: "banner error", role: "alert" }, error),
    el("div", { className: "actions" }, el("button", { type: "submit", className: "primary" }, "Сохранить"), el("button", { type: "button", className: "secondary", onclick: onCancel }, "Отмена")),
  );
}

export function deckCardsView({ deck, cards, onSave, onBack }) {
  const members = new Set(deck.card_ids);
  const boxes = cards.map((card) => {
    const box = el("input", { type: "checkbox", value: String(card.id) });
    box.checked = members.has(card.id);
    return box;
  });
  const counter = el("span", { className: "meta" });
  const refresh = () => {
    counter.textContent = `Выбрано: ${boxes.filter((box) => box.checked).length} из ${cards.length}`;
  };
  boxes.forEach((box) => box.addEventListener("change", refresh));
  refresh();

  const rows = cards.map((card, index) => ({
    card,
    node: el(
      "li",
      { className: "row" },
      el(
        "label",
        { className: "deck-option" },
        boxes[index],
        el("span", {}, el("strong", {}, card.term), " ", el("span", { className: "badge" }, card.domain), !card.verified && el("span", { className: "badge bad" }, "не проверена")),
      ),
    ),
  }));
  const search = el("input", { type: "search", id: "deck-card-search", placeholder: "Поиск по термину" });
  search.addEventListener("input", () => {
    const query = search.value.trim().toLowerCase();
    rows.forEach(({ card, node }) => {
      node.hidden = query !== "" && !card.term.toLowerCase().includes(query);
    });
  });

  return el(
    "section",
    { className: "card" },
    el("h2", {}, `Состав набора: ${deck.name}`),
    el("p", { className: "meta" }, "Студентам видны только проверенные карточки набора. Личные карточки студентов сюда не входят."),
    search,
    counter,
    el("ul", { className: "list" }, rows.map((row) => row.node)),
    el(
      "div",
      { className: "actions" },
      el("button", { type: "button", className: "primary", onclick: () => onSave(boxes.filter((box) => box.checked).map((box) => Number(box.value))) }, "Сохранить состав"),
      el("button", { type: "button", className: "secondary", onclick: onBack }, "Назад"),
    ),
  );
}

export function personalView({ cards, owners, owner, onOwner, onOpen }) {
  const select = el(
    "select",
    { "aria-label": "Автор" },
    el("option", { value: "" }, "Все студенты"),
    owners.map((name) => el("option", { value: name }, name)),
  );
  select.value = owner;
  select.addEventListener("change", () => onOwner(select.value));
  const rows = cards.map((card) => {
    const marked = Object.values(card.sources).filter((source) => source === "llm").length;
    return el(
      "li",
      { className: "row" },
      el(
        "div",
        { className: "info" },
        el("strong", {}, card.term),
        " ",
        el("span", { className: "badge" }, card.domain),
        el("span", { className: "badge" }, `автор: ${card.owner}`),
        card.shared_duplicate && el("span", { className: "badge bad" }, "такой термин уже есть в общих"),
        marked > 0 && el("span", { className: "badge src-llm" }, `полей от модели: ${marked}`),
        el("div", { className: "definition" }, card.definition_en),
      ),
      el("div", { className: "buttons" }, el("button", { type: "button", className: "primary", onclick: () => onOpen(card) }, "Открыть")),
    );
  });
  return el(
    "section",
    { className: "card" },
    el("div", { className: "toolbar" }, select, el("span", { className: "meta" }, `Показано: ${cards.length}`)),
    el("p", { className: "meta" }, "Личные карточки видны только автору и вам. В аналитику группы они не входят, пока вы не поднимете их в общий набор."),
    cards.length ? el("ul", { className: "list" }, rows) : el("p", {}, "Личных карточек пока нет."),
  );
}

export function personalCardView({ card, decks, domains, error = "", notice = "", onSave, onPromote, onBack }) {
  const base = cardFormView({ card, domains, error: "", onSave, onCancel: onBack });
  const boxes = decks.map((deck) => {
    const box = el("input", { type: "checkbox", id: `p-deck-${deck.id}`, value: String(deck.id) });
    return box;
  });
  const promote = el("button", { type: "button", className: "primary", disabled: true }, "Поднять в общий набор");
  boxes.forEach((box) => box.addEventListener("change", () => {
    promote.disabled = !boxes.some((item) => item.checked);
  }));
  promote.addEventListener("click", () => onPromote(boxes.filter((box) => box.checked).map((box) => Number(box.value))));

  const legend = Object.entries(card.sources).map(([field, source]) =>
    el("span", { className: SOURCE_CLASS[source] || "badge" }, `${field}: ${SOURCE_LABELS[source] || source}`),
  );
  return el(
    "div",
    {},
    el("section", { className: "card" },
      el("h2", {}, `Личная карточка: ${card.term}`),
      el("p", { className: "meta" }, `Автор: ${card.owner}. Источники полей:`),
      el("div", { className: "error-chips" }, legend),
      card.shared_duplicate && el("p", { className: "banner warn", role: "status" }, "Общая карточка с таким термином уже есть: поднять эту нельзя."),
      notice && el("p", { className: "banner ok", role: "status" }, notice),
      error && el("p", { className: "banner error", role: "alert" }, error),
    ),
    base,
    el(
      "section",
      { className: "card" },
      el("h3", {}, "Поднять в общий набор"),
      el("p", { className: "meta" }, "Карточка станет общей и проверенной: ее увидят студенты, выбравшие эти наборы. Прогресс и история автора сохранятся. Сначала проверьте и при необходимости поправьте поля выше и сохраните их."),
      decks.map((deck, index) =>
        el("label", { className: "deck-option", for: `p-deck-${deck.id}` }, boxes[index], el("span", {}, el("strong", {}, deck.name), " ", el("span", { className: "badge" }, deck.domain))),
      ),
      promote,
    ),
  );
}
