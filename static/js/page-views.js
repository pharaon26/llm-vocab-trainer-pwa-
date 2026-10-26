import { el } from "./dom.js";
import { barChart } from "./charts.js";
import { describeDate, percent, plural } from "./format.js";
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
          item.is_practice && el("span", { className: "badge" }, "тренировка"),
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

export function statsView({ data }) {
  const { streak, totals } = data;
  const shortDate = (iso) => new Date(`${iso}T00:00:00`).toLocaleDateString("ru-RU", { day: "numeric", month: "short" });
  const dayRows = data.days.map((day) => ({
    label: shortDate(day.date),
    value: day.accuracy ?? 0,
    text: day.answered ? `${day.correct} из ${day.answered} (${percent(day.accuracy)})` : "нет ответов",
  }));
  const errorRows = data.error_types.map((item) => ({
    label: ERROR_LABELS[item.error_type],
    value: item.share,
    text: `${item.count} (${percent(item.share)})`,
  }));
  const hasErrors = data.error_types.some((item) => item.count > 0);
  const streakText = (n) => `${n} ${plural(n, "день", "дня", "дней")}`;

  return el(
    "section",
    { className: "card" },
    el("h2", {}, "Моя статистика"),
    el(
      "div",
      { className: "summary" },
      el("div", {}, el("strong", {}, streakText(streak.current)), "серия подряд"),
      el("div", {}, el("strong", {}, streakText(streak.best)), "лучшая серия"),
      el("div", {}, el("strong", {}, String(totals.answered)), "ответов"),
      el("div", {}, el("strong", {}, totals.accuracy == null ? "-" : percent(totals.accuracy)), "точность"),
    ),
    el(
      "p",
      { className: "meta" },
      `Серия: дни подряд, когда вы отвечали на задания (тренировка тоже считается). Точность и ошибки считаются по первым ответам в сессии, повторы после ошибки и тренировка не входят. Ответов в свободной тренировке за период: ${data.days.reduce((sum, day) => sum + day.practice, 0)}.`,
    ),
    el("h3", {}, `Точность по дням (последние ${data.days.length})`),
    barChart("Точность по дням", dayRows),
    el("h3", {}, "Мои ошибки по типам"),
    hasErrors ? barChart("Мои ошибки по типам", errorRows) : el("p", {}, "Ошибок пока нет."),
  );
}

export function settingsView({ settings, decks, notice = "", error = "", onSave }) {
  const output = el("output", { for: "per-day", className: "per-day" }, String(settings.new_cards_per_day));
  const range = el("input", {
    id: "per-day",
    type: "range",
    min: settings.min_new_per_day,
    max: settings.max_new_per_day,
    step: 1,
    value: settings.new_cards_per_day,
  });
  range.addEventListener("input", () => {
    output.textContent = range.value;
  });

  const boxes = decks.map((deck) => {
    const box = el("input", { type: "checkbox", id: `deck-${deck.id}`, value: String(deck.id) });
    box.checked = deck.selected;
    return box;
  });
  const deckList = el(
    "fieldset",
    { className: "decks" },
    el("legend", {}, "Наборы для изучения"),
    decks.length
      ? decks.map((deck, index) =>
          el(
            "label",
            { className: "deck-option", for: `deck-${deck.id}` },
            boxes[index],
            el(
              "span",
              {},
              el("strong", {}, deck.name),
              " ",
              el("span", { className: "badge" }, deck.domain),
              el("span", { className: "meta" }, ` ${deck.cards} карточек`),
              deck.description && el("span", { className: "definition" }, deck.description),
            ),
          ),
        )
      : el("p", {}, "Наборов пока нет."),
    el(
      "p",
      { className: "meta" },
      "Новые термины берутся только из выбранных наборов. Повторения уже открытых терминов продолжаются, даже если набор снят.",
    ),
  );

  return el(
    "section",
    { className: "card" },
    el("h2", {}, "Настройки"),
    el("label", { for: "per-day" }, "Новых терминов в день: ", output),
    range,
    el(
      "p",
      { className: "meta" },
      `От ${settings.min_new_per_day} до ${settings.max_new_per_day}. Столько новых терминов открывается в повторении каждый день, кроме тех, что нужно повторить по расписанию. Изменение действует сразу.`,
    ),
    deckList,
    notice && el("p", { className: "banner ok", role: "status" }, notice),
    error && el("p", { className: "banner error", role: "alert" }, error),
    el(
      "button",
      {
        type: "button",
        className: "primary",
        onclick: () => onSave({ perDay: Number(range.value), deckIds: boxes.filter((box) => box.checked).map((box) => Number(box.value)) }),
      },
      "Сохранить",
    ),
  );
}

const SOURCE_LABELS = { dictionary: "словарь", llm: "модель: проверьте", user: "вы" };
const SOURCE_CLASS = { dictionary: "badge src-dictionary", llm: "badge src-llm", user: "badge src-user" };

const WORD_FIELDS = [
  ["transcription", "Транскрипция", "text"],
  ["part_of_speech", "Часть речи", "text"],
  ["definition_en", "Определение (English)", "area"],
  ["translation_ru", "Перевод на русский", "text"],
  ["collocations", "Словосочетания", "lines", "2-4, по одному в строке"],
  ["examples", "Примеры", "lines", "2-3, по одному в строке"],
  ["common_mistakes", "Типичные ошибки", "lines", "по одной в строке"],
  ["contrast_term", "Контрастный термин", "text", "необязательно"],
];

export function dictionaryView({ entries, drafts, myCards, onAdd, onAddFromText, onOpenDraft, onDeleteDraft, onEditCard, onDeleteCard }) {
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
          entry.personal && el("span", { className: "badge" }, "моя"),
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

  const draftRows = drafts.map((draft) =>
    el(
      "li",
      { className: "row" },
      el(
        "div",
        { className: "info" },
        el("strong", {}, draft.term),
        " ",
        el("span", { className: "badge" }, draft.domain),
        el("div", { className: "definition" }, draft.missing.length ? `Не заполнено полей: ${draft.missing.length}` : "Готов к подтверждению"),
      ),
      el(
        "div",
        { className: "buttons" },
        el("button", { type: "button", className: "primary", onclick: () => onOpenDraft(draft) }, "Продолжить"),
        el("button", { type: "button", className: "danger", onclick: () => onDeleteDraft(draft) }, "Удалить"),
      ),
    ),
  );
  const cardRows = myCards.map((card) =>
    el(
      "li",
      { className: "row" },
      el(
        "div",
        { className: "info" },
        el("strong", {}, card.term),
        " ",
        el("span", { className: "badge" }, card.domain),
        el("div", { className: "definition" }, card.translation_ru),
      ),
      el(
        "div",
        { className: "buttons" },
        el("button", { type: "button", onclick: () => onEditCard(card) }, "Изменить"),
        el("button", { type: "button", className: "danger", onclick: () => onDeleteCard(card) }, "Удалить"),
      ),
    ),
  );

  return el(
    "section",
    { className: "card" },
    el("h2", {}, "Словарь"),
    el(
      "div",
      { className: "toolbar" },
      el("button", { type: "button", className: "primary", onclick: onAdd }, "Добавить термин"),
      el("button", { type: "button", onclick: onAddFromText }, "Добавить из текста"),
    ),
    drafts.length > 0 && [
      el("h3", {}, "Черновики"),
      el("p", { className: "meta" }, "Черновик попадает в повторения только после вашей проверки и подтверждения."),
      el("ul", { className: "list" }, draftRows),
    ],
    myCards.length > 0 && [el("h3", {}, "Мои слова"), el("ul", { className: "list" }, cardRows)],
    el("h3", {}, "Открытые термины"),
    entries.length
      ? [el("p", { className: "meta" }, `Открытых терминов: ${entries.length}`), search, list, empty]
      : el("p", {}, "Здесь появятся термины, которые вы откроете в повторении."),
  );
}

export function addTermView({ domains, term = "", domain = "", error = "", onSubmit, onCancel }) {
  const input = el("input", { id: "new-term", type: "text", maxlength: 100, required: true, autocomplete: "off", placeholder: "Например, latency или man-in-the-middle attack" });
  input.value = term;
  const select = el("select", { id: "new-domain", required: true }, domains.map((item) => el("option", { value: item.name }, item.name)));
  if (domain) {
    select.value = domain;
  }
  return el(
    "form",
    {
      className: "card",
      onsubmit: (event) => {
        event.preventDefault();
        onSubmit(input.value.trim(), select.value);
      },
    },
    el("h2", {}, "Добавить термин"),
    el("label", { for: "new-term" }, "Слово или словосочетание"),
    input,
    el("label", { for: "new-domain" }, "Область"),
    select,
    el("p", { className: "meta" }, "Приложение соберет черновик карточки: данные из словаря, недостающее предложит модель. Вы просмотрите, поправите и подтвердите."),
    error && el("p", { className: "banner error", role: "alert" }, error),
    el("div", { className: "actions" }, el("button", { type: "submit", className: "primary" }, "Подобрать данные"), el("button", { type: "button", className: "secondary", onclick: onCancel }, "Отмена")),
  );
}

export function duplicateView({ duplicate, onBack, onEnableDeck }) {
  return el(
    "section",
    { className: "card" },
    el("h2", {}, "Такой термин уже есть"),
    el("p", {}, el("strong", {}, duplicate.term), " ", el("span", { className: "badge" }, duplicate.domain), duplicate.personal && el("span", { className: "badge" }, "моя карточка")),
    el("p", {}, duplicate.definition_en),
    duplicate.personal
      ? el("p", { className: "meta" }, "Это ваша личная карточка, она уже в повторениях.")
      : duplicate.decks.length
        ? [
            el("p", { className: "meta" }, "Общая карточка входит в наборы:"),
            el(
              "ul",
              { className: "list" },
              duplicate.decks.map((deck) =>
                el(
                  "li",
                  { className: "row" },
                  el("div", { className: "info" }, el("strong", {}, deck.name), " ", el("span", { className: deck.selected ? "badge ok" : "badge" }, deck.selected ? "выбран" : "не выбран")),
                  !deck.selected && el("button", { type: "button", onclick: () => onEnableDeck(deck) }, "Включить набор"),
                ),
              ),
            ),
          ]
        : el("p", { className: "meta" }, "Карточка общая, но пока не входит ни в один набор."),
    el("button", { type: "button", className: "primary", onclick: onBack }, "Понятно"),
  );
}

export function draftEditorView({ draft, domains, mode = "draft", error = "", notice = "", onSave, onConfirm, onDelete, onCancel }) {
  const inputs = {};
  const badges = {};
  const sources = { ...draft.sources };

  const rows = WORD_FIELDS.map(([name, label, kind, hint]) => {
    const input = el(kind === "text" ? "input" : "textarea", { id: `w-${name}`, type: kind === "text" ? "text" : null, rows: kind === "text" ? null : kind === "lines" ? 4 : 3 });
    const value = draft.fields[name];
    input.value = Array.isArray(value) ? value.join("\n") : (value ?? "");
    inputs[name] = [input, kind];
    const badge = el("span", { className: "source-slot" });
    badges[name] = badge;
    const paint = () => {
      badge.replaceChildren();
      const source = sources[name];
      if (source) {
        badge.append(" ", el("span", { className: SOURCE_CLASS[source] }, SOURCE_LABELS[source]));
      } else if (!input.value.trim() && name !== "contrast_term") {
        badge.append(" ", el("span", { className: "badge bad" }, "заполните"));
      }
    };
    paint();
    input.addEventListener("input", () => {
      sources[name] = "user";
      paint();
    });
    return el(
      "div",
      { className: "field" },
      el("label", { for: `w-${name}` }, label, hint && el("span", { className: "hint" }, ` (${hint})`), badge),
      input,
      name === "definition_en" && draft.general_definition && el("p", { className: "meta" }, `Общее определение из словаря: ${draft.general_definition}`),
    );
  });

  const select = el("select", { id: "w-domain" }, domains.map((item) => el("option", { value: item.name }, item.name)));
  select.value = draft.domain;

  const collect = () => {
    const fields = {};
    for (const [name, [input, kind]] of Object.entries(inputs)) {
      fields[name] = kind === "lines" ? input.value.split("\n").map((line) => line.trim()).filter(Boolean) : input.value.trim();
    }
    return { fields, domain: select.value };
  };

  return el(
    "form",
    {
      className: "card",
      onsubmit: (event) => {
        event.preventDefault();
        (mode === "draft" ? onConfirm : onSave)(collect());
      },
    },
    el("h2", {}, mode === "draft" ? `Черновик: ${draft.term}` : `Изменить: ${draft.term}`),
    mode === "draft" && el("p", { className: "meta" }, "Проверьте каждое поле. Поля, предложенные моделью, помечены: они могут содержать неточности."),
    draft.notices.map((text) => el("p", { className: "banner warn", role: "status" }, text)),
    el("div", { className: "field" }, el("label", { for: "w-domain" }, "Область"), select),
    draft.audio_url && el("audio", { controls: true, preload: "none", src: draft.audio_url }),
    rows,
    notice && el("p", { className: "banner ok", role: "status" }, notice),
    error && el("p", { className: "banner error", role: "alert" }, error),
    el(
      "div",
      { className: "actions" },
      mode === "draft"
        ? [
            el("button", { type: "submit", className: "primary" }, "Подтвердить"),
            el("button", { type: "button", onclick: () => onSave(collect()) }, "Сохранить черновик"),
          ]
        : el("button", { type: "submit", className: "primary" }, "Сохранить"),
      el("button", { type: "button", className: "secondary", onclick: onCancel }, "Назад"),
    ),
    mode === "draft" && el("button", { type: "button", className: "link", onclick: onDelete }, "Удалить черновик"),
  );
}

export function extractView({ domains, limits, text = "", domain = "", error = "", onSubmit, onCancel }) {
  const area = el("textarea", { id: "source-text", rows: 10, placeholder: "Вставьте фрагмент документации или статьи на английском" });
  area.value = text;
  const select = el("select", { id: "source-domain" }, domains.map((item) => el("option", { value: item.name }, item.name)));
  if (domain) {
    select.value = domain;
  }
  const counter = el("span", { className: "meta" });
  const submit = el("button", { type: "submit", className: "primary" }, "Найти термины");
  const refresh = () => {
    const length = area.value.trim().length;
    counter.textContent = `${length} / ${limits.extract_max_chars}`;
    counter.className = length > limits.extract_max_chars ? "meta over" : "meta";
    submit.disabled = length === 0 || length > limits.extract_max_chars || limits.llm_calls_left <= 0;
  };
  area.addEventListener("input", refresh);
  refresh();

  return el(
    "form",
    {
      className: "card",
      onsubmit: (event) => {
        event.preventDefault();
        onSubmit(area.value.trim(), select.value);
      },
    },
    el("h2", {}, "Добавить из текста"),
    el(
      "p",
      { className: "banner warn", role: "note" },
      "Не вставляйте конфиденциальные данные: текст отправляется во внешнюю языковую модель (GigaChat). Текст не сохраняется в приложении.",
    ),
    el("label", { for: "source-text" }, "Фрагмент текста"),
    area,
    counter,
    el("label", { for: "source-domain" }, "Область"),
    select,
    el(
      "p",
      { className: "meta" },
      `Модель предложит до ${limits.extract_max_terms} профессиональных терминов из текста. Для каждого отмеченного будет создан черновик. Обращений к модели сегодня осталось: ${limits.llm_calls_left} из ${limits.daily_llm_limit}.`,
    ),
    error && el("p", { className: "banner error", role: "alert" }, error),
    el("div", { className: "actions" }, submit, el("button", { type: "button", className: "secondary", onclick: onCancel }, "Отмена")),
  );
}

export function candidatesView({ candidates, domain, onCreate, onBack }) {
  const boxes = candidates.map((candidate) => {
    const box = el("input", { type: "checkbox", value: candidate.term });
    box.checked = !candidate.exists && !candidate.has_draft;
    box.disabled = candidate.exists || candidate.has_draft;
    return box;
  });
  const create = el("button", { type: "button", className: "primary" }, "");
  const refresh = () => {
    const count = boxes.filter((box) => box.checked).length;
    create.textContent = `Создать черновики (${count})`;
    create.disabled = count === 0;
  };
  boxes.forEach((box) => box.addEventListener("change", refresh));
  create.addEventListener("click", () => onCreate(boxes.filter((box) => box.checked).map((box) => box.value)));
  refresh();

  return el(
    "section",
    { className: "card" },
    el("h2", {}, "Найденные термины"),
    el("p", { className: "meta" }, `Область: ${domain}. Отметьте термины, которые хотите учить.`),
    candidates.length
      ? el(
          "ul",
          { className: "list" },
          candidates.map((candidate, index) =>
            el(
              "li",
              { className: "row" },
              el(
                "label",
                { className: "deck-option" },
                boxes[index],
                el(
                  "span",
                  {},
                  el("strong", {}, candidate.term),
                  candidate.exists && el("span", { className: "badge" }, candidate.personal ? "уже в моих словах" : "уже есть в общих"),
                  candidate.has_draft && el("span", { className: "badge" }, "черновик уже создан"),
                ),
              ),
            ),
          ),
        )
      : el("p", {}, "Подходящих терминов в тексте не нашлось."),
    el("div", { className: "actions" }, candidates.length ? create : null, el("button", { type: "button", className: "secondary", onclick: onBack }, "Назад")),
  );
}
