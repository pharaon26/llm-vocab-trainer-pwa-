import { emptyState, icon, skeleton } from "./components.js";
import { el } from "./dom.js";
import { describeDate } from "./format.js";

export const ERROR_LABELS = {
  form: "форма (написание)",
  meaning: "значение",
  usage: "употребление",
  collocation: "словосочетание",
};

const MULTILINE_TASKS = ["explain_meaning", "compose_sentence"];

export function loadingView(text) {
  return skeleton(text);
}

export function messageView(title, text, buttonText, onClick, iconName = "inbox", error = false) {
  return emptyState({ iconName, title, text, action: { label: buttonText, onClick }, error });
}

function nameInput(name) {
  const input = el("input", {
    id: "name",
    type: "text",
    maxlength: 50,
    required: true,
    autocomplete: "username",
    pattern: "[A-Za-z0-9_]{3,32}",
    title: "Латиница, цифры и подчеркивание, 3-32 символа",
    placeholder: "например, anna_k",
  });
  input.value = name;
  return input;
}

function passwordInput(id, autocomplete) {
  return el("input", {
    id,
    type: "password",
    minlength: 8,
    maxlength: 128,
    required: true,
    autocomplete,
  });
}

export function loginView({ name = "", error = "", onSubmit, onShowRegister }) {
  const input = nameInput(name);
  const password = passwordInput("password", "current-password");
  return el(
    "form",
    {
      className: "card",
      onsubmit: (event) => {
        event.preventDefault();
        onSubmit(input.value.trim(), password.value);
      },
    },
    el("h2", {}, "Вход"),
    el("label", { for: "name" }, "Ник"),
    input,
    el("label", { for: "password" }, "Пароль"),
    password,
    error && el("p", { className: "banner error", role: "alert" }, error),
    el("button", { type: "submit", className: "primary" }, "Войти"),
    el("p", {}, "Нет аккаунта? ", el("button", { type: "button", className: "link", onclick: () => onShowRegister(input.value.trim()) }, "Создать аккаунт")),
  );
}

export function registerView({ name = "", error = "", onSubmit, onShowLogin }) {
  const input = nameInput(name);
  const password = passwordInput("password", "new-password");
  const confirm = passwordInput("password-confirm", "new-password");
  const teacher = el("input", { id: "is-teacher", type: "checkbox" });
  const checkMatch = () => confirm.setCustomValidity(confirm.value === password.value ? "" : "Пароли не совпадают");
  password.addEventListener("input", checkMatch);
  confirm.addEventListener("input", checkMatch);
  return el(
    "form",
    {
      className: "card",
      onsubmit: (event) => {
        event.preventDefault();
        checkMatch();
        if (confirm.reportValidity()) {
          onSubmit(input.value.trim(), password.value, confirm.value, teacher.checked ? "teacher" : "student");
        }
      },
    },
    el("h2", {}, "Регистрация"),
    el("label", { for: "name" }, "Ник (латиница, цифры, _; 3-32 символа)"),
    input,
    el("label", { for: "password" }, "Пароль (не короче 8 символов)"),
    password,
    el("label", { for: "password-confirm" }, "Повторите пароль"),
    confirm,
    el("label", { className: "check", for: "is-teacher" }, teacher, " Я преподаватель"),
    error && el("p", { className: "banner error", role: "alert" }, error),
    el("button", { type: "submit", className: "primary" }, "Зарегистрироваться"),
    el("p", {}, "Уже есть аккаунт? ", el("button", { type: "button", className: "link", onclick: () => onShowLogin(input.value.trim()) }, "Войти")),
  );
}

export function startView({ name, onStart }) {
  return el(
    "section",
    { className: "card" },
    el("h2", {}, `Привет, ${name}!`),
    el("p", {}, "Повторение на сегодня: сначала вспомните ответ, потом смотрите эталон."),
    el("button", { type: "button", className: "primary", onclick: onStart }, "Начать повторение"),
  );
}

export function taskView(task, meta, { draft, onDraft, onSubmit, onExit, progress = null }) {
  let selected = null;
  let busy = false;
  let input = null;
  let optionButtons = [];

  const banner = el("p", { className: "banner error", role: "alert", hidden: true });
  const submit = el("button", { type: "button", className: "primary" }, "Ответить");
  const skip = el("button", { type: "button", className: "secondary" }, "Не знаю");

  const answerText = () => (input ? input.value.trim() : (selected ?? ""));
  const refresh = () => {
    submit.disabled = busy || answerText() === "";
    skip.disabled = busy;
    optionButtons.forEach((button) => (button.disabled = busy));
    if (input) {
      input.disabled = busy;
    }
  };

  let control;
  if (task.options) {
    optionButtons = task.options.map((option) => {
      const button = el("button", { type: "button", className: "option", role: "radio", "aria-checked": "false" }, option);
      button.addEventListener("click", () => {
        selected = option;
        optionButtons.forEach((other) => other.setAttribute("aria-checked", String(other === button)));
        refresh();
      });
      return button;
    });
    control = el("div", { className: "options", role: "radiogroup" }, optionButtons);
  } else {
    const multiline = MULTILINE_TASKS.includes(task.task_type);
    input = el(multiline ? "textarea" : "input", {
      id: "answer",
      "aria-label": "Ваш ответ",
      autocomplete: "off",
      autocapitalize: "off",
      spellcheck: "false",
      rows: multiline ? 4 : null,
      type: multiline ? null : "text",
    });
    input.value = draft;
    input.addEventListener("input", () => {
      onDraft(input.value);
      refresh();
    });
    if (!multiline) {
      input.addEventListener("keydown", (event) => {
        if (event.key === "Enter" && !submit.disabled) {
          onSubmit(answerText());
        }
      });
    }
    control = input;
  }

  submit.addEventListener("click", () => onSubmit(answerText()));
  skip.addEventListener("click", () => onSubmit(""));

  const node = el(
    "section",
    { className: "card" },
    progress && el("progress", { className: "session-progress", value: progress.value, max: progress.max, "aria-label": "Прогресс сессии" }),
    el("p", { className: "meta" }, meta),
    el("h2", {}, task.instruction),
    el("p", { className: "prompt" }, task.prompt),
    task.context && el("p", { className: "context" }, task.context),
    control,
    banner,
    el("div", { className: "actions" }, submit, skip),
    onExit && el("button", { type: "button", className: "link", onclick: onExit }, "Закончить тренировку"),
  );
  refresh();

  return {
    node,
    setBusy(value) {
      busy = value;
      submit.textContent = value ? "Проверяем…" : "Ответить";
      refresh();
    },
    showError(message) {
      banner.textContent = message;
      banner.hidden = false;
    },
  };
}

function list(title, items) {
  return el("div", {}, el("h4", {}, title), el("ul", {}, items.map((item) => el("li", {}, item))));
}

function cardReference(card) {
  return el(
    "section",
    { className: "reference" },
    el(
      "h3",
      {},
      card.term,
      " ",
      el("span", { className: "ipa" }, card.transcription),
      " ",
      el("span", { className: "pos" }, card.part_of_speech),
    ),
    el("p", {}, card.definition_en),
    el("p", { className: "translation" }, card.translation_ru),
    list("Словосочетания", card.collocations),
    list("Примеры", card.examples),
    list("Частые ошибки", card.common_mistakes),
    card.contrast_term && el("p", {}, el("strong", {}, "Не путать с: "), card.contrast_term),
  );
}

export function feedbackView(result, userAnswer, { onNext, onExit }) {
  const verdict = result.correct
    ? "Верно!"
    : `Неверно${result.error_type ? `: ${ERROR_LABELS[result.error_type]}` : ""}`;
  const next = el("button", { type: "button", className: "primary", onclick: onNext }, "Дальше");

  const node = el(
    "section",
    { className: `card feedback ${result.correct ? "ok" : "bad"}` },
    el("p", { className: "meta" }, onExit ? "Тренировка: расписание повторений не меняется" : `Осталось: ${result.remaining}`),
    el("h2", { className: result.correct ? "ok" : "bad" }, verdict),
    !result.correct && el("p", {}, el("strong", {}, "Ваш ответ: "), userAnswer || "(пусто)"),
    !result.correct && el("p", {}, el("strong", {}, "Эталон: "), result.correct_answer),
    result.comment && el("p", { className: "note" }, result.comment),
    result.retry_in_session && el("p", { className: "meta" }, "Этот термин вернется в конце сессии."),
    cardReference(result.card),
    next,
    onExit && el("button", { type: "button", className: "secondary", onclick: onExit }, "Закончить тренировку"),
  );
  return { node, focus: () => next.focus() };
}

export function doneView({ answered, correct, info, checkedAt, onRefresh, onPractice }) {
  const noCards = answered === 0 && !info.next_review_date && info.unseen_cards === 0;
  if (noCards) {
    return emptyState({
      iconName: "book-open",
      title: "Заданий пока нет",
      text: "Выберите наборы для изучения в настройках или загляните позже: возможно, карточки еще не проверены или преподаватель не назначил вам набор.",
      action: { label: "Проверить снова", onClick: onRefresh },
    });
  }
  return el(
    "section",
    { className: "card" },
    el("div", { className: "empty" }, icon("circle-check", 52), el("h2", {}, "На сегодня всё")),
    answered > 0 && el("p", {}, `Верных ответов в этой сессии: ${correct} из ${answered}.`),
    info.next_review_date && el("p", {}, `Следующее повторение: ${describeDate(info.next_review_date)}.`),
    info.unseen_cards > 0 &&
      el("p", {}, `Новые термины открываются по ${info.new_cards_per_day} в день, осталось новых: ${info.unseen_cards}.`),
    el("p", { className: "meta" }, "Задания на сегодня выполнены, возвращайтесь по расписанию."),
    checkedAt && el("p", { className: "meta" }, `Проверено в ${checkedAt}: новых заданий нет.`),
    info.opened_cards > 0 &&
      el("button", { type: "button", className: "primary", onclick: onPractice }, "Свободная тренировка"),
    el("button", { type: "button", className: "secondary", onclick: onRefresh }, "Проверить снова"),
  );
}
