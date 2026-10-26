import { el } from "./dom.js";
import { describeDate } from "./format.js";
import { ERROR_LABELS } from "./views.js";

const STATUS_LABELS = { new: "новый", learning: "изучаю", learned: "выучен" };
const STATUS_CLASS = { new: "badge", learning: "badge", learned: "badge ok" };

export function chipsView(options, active, onSelect) {
  return el(
    "div",
    { className: "chips", role: "group" },
    options.map(([id, label]) =>
      el("button", { type: "button", "aria-pressed": String(id === active), onclick: () => onSelect(id) }, label),
    ),
  );
}

export function progressView({ data, filter, onFilter }) {
  const { summary } = data;
  const items = filter === "all" ? data.items : data.items.filter((item) => item.status === filter);
  const rows = items.map((item) => {
    const errors = Object.entries(item.errors).filter(([, count]) => count > 0);
    return el(
      "li",
      { className: "row" },
      el(
        "div",
        { className: "info" },
        el("strong", {}, item.term),
        " ",
        el("span", { className: STATUS_CLASS[item.status] }, STATUS_LABELS[item.status]),
        el(
          "div",
          { className: "definition" },
          item.due_date ? `Следующее повторение: ${describeDate(item.due_date)}` : "Еще не открыт",
        ),
        errors.length > 0 &&
          el(
            "div",
            { className: "error-chips" },
            errors.map(([type, count]) => el("span", { className: "badge bad" }, `${ERROR_LABELS[type]}: ${count}`)),
          ),
      ),
    );
  });
  return el(
    "section",
    { className: "card" },
    el("h2", {}, "Мой прогресс"),
    el(
      "div",
      { className: "summary" },
      el("div", {}, el("strong", {}, String(summary.learned)), "выучено"),
      el("div", {}, el("strong", {}, String(summary.learning)), "изучаю"),
      el("div", {}, el("strong", {}, String(summary.new)), "новых"),
    ),
    el("p", { className: "meta" }, "Выучен: интервал повторения от 21 дня и нет ошибки, ожидающей повтора. Ошибки считаются по первым ответам в сессии."),
    chipsView(
      [["all", "Все"], ["learning", "Изучаю"], ["new", "Новые"], ["learned", "Выучены"]],
      filter,
      onFilter,
    ),
    rows.length ? el("ul", { className: "list" }, rows) : el("p", {}, "В этой группе терминов нет."),
  );
}

const TASK_LABELS = {
  spelling_choice: "написание",
  definition_match: "определение",
  gap_fill: "пропуск",
  collocation_choice: "словосочетание",
  write_term: "ввод термина",
  explain_meaning: "объяснение",
  compose_sentence: "предложение",
};

function formatDay(isoDate) {
  return new Date(`${isoDate}T00:00:00`).toLocaleDateString("ru-RU", { day: "numeric", month: "long", year: "numeric" });
}

export function historyView({ terms, term, items, total, onTerm, onMore }) {
  const select = el(
    "select",
    { id: "term-filter", "aria-label": "Термин" },
    el("option", { value: "" }, "Все термины"),
    terms.map((name) => el("option", { value: name }, name)),
  );
  select.value = term;
  select.addEventListener("change", () => onTerm(select.value));

  const rows = items.map((item) =>
    el(
      "li",
      { className: "row history-row" },
      el(
        "div",
        { className: "info" },
        el(
          "div",
          {},
          el("strong", {}, item.term),
          " ",
          el("span", { className: "badge" }, TASK_LABELS[item.task_type] || item.task_type),
          " ",
          el("span", { className: item.is_correct ? "badge ok" : "badge bad" }, item.is_correct ? "верно" : `ошибка: ${ERROR_LABELS[item.error_type]}`),
          item.is_retry && el("span", { className: "badge" }, "повтор"),
          el("span", { className: "meta" }, ` ${formatDay(item.answered_on)}`),
        ),
        el("p", { className: "definition" }, el("strong", {}, "Задание: "), item.prompt),
        el("p", {}, el("strong", {}, "Мой ответ: "), item.answer || "(пусто)"),
        !item.is_correct && el("p", {}, el("strong", {}, "Правильно: "), item.correct_answer),
        item.comment && el("p", { className: "note" }, item.comment),
      ),
    ),
  );
  return el(
    "section",
    { className: "card" },
    el("h2", {}, "История ответов"),
    el("div", { className: "toolbar" }, el("label", { for: "term-filter" }, "Термин:"), select),
    el("p", { className: "meta" }, `Показано ${items.length} из ${total}`),
    rows.length ? el("ul", { className: "list" }, rows) : el("p", {}, "Ответов пока нет."),
    items.length < total && el("button", { type: "button", onclick: onMore }, "Показать еще"),
  );
}

export function dictionaryView({ entries }) {
  const list = el("ul", { className: "list" });
  const empty = el("p", { hidden: true }, "Ничего не найдено.");

  const items = entries.map((entry) => ({
    entry,
    node: el(
      "li",
      { className: "row" },
      el(
        "details",
        { className: "info dictionary-entry" },
        el(
          "summary",
          {},
          el("strong", {}, entry.term),
          " ",
          el("span", { className: "ipa" }, entry.transcription),
          " ",
          el("span", { className: "pos" }, entry.part_of_speech),
          el("div", { className: "translation" }, entry.translation_ru),
        ),
        el("p", {}, entry.definition_en),
        el("h4", {}, "Словосочетания"),
        el("ul", {}, entry.collocations.map((item) => el("li", {}, item))),
        el("h4", {}, "Примеры"),
        el("ul", {}, entry.examples.map((item) => el("li", {}, item))),
      ),
    ),
  }));
  list.append(...items.map((item) => item.node));

  const search = el("input", { type: "search", id: "dictionary-search", placeholder: "Поиск по термину или переводу", autocomplete: "off" });
  search.addEventListener("input", () => {
    const query = search.value.trim().toLowerCase();
    let visible = 0;
    for (const { entry, node } of items) {
      const match = !query || entry.term.toLowerCase().includes(query) || entry.translation_ru.toLowerCase().includes(query);
      node.hidden = !match;
      visible += match ? 1 : 0;
    }
    empty.hidden = visible > 0;
  });

  return el(
    "section",
    { className: "card" },
    el("h2", {}, "Словарь"),
    entries.length
      ? [el("p", { className: "meta" }, `Открытых терминов: ${entries.length}`), search, list, empty]
      : el("p", {}, "Здесь появятся термины, которые вы откроете в повторении."),
  );
}
