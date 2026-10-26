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
