import * as api from "./api.js";
import { show, unauthorized } from "./ui.js";
import * as views from "./views.js";

const stats = { answered: 0, correct: 0 };

export function resetStats() {
  stats.answered = 0;
  stats.correct = 0;
}

export function showStart() {
  show(views.startView({ name: api.getName(), onStart: () => loadNext() }));
}

function showFailure(error) {
  if (error.status === 401) {
    unauthorized();
    return;
  }
  show(views.messageView("Не удалось загрузить задание", error.message, "Повторить", () => loadNext()));
}

async function loadNext(quiet = false) {
  if (!quiet) {
    show(views.loadingView("Готовим задание…"));
  }
  try {
    const data = await api.nextTask();
    if (data.task) {
      showTask(data.task, data.remaining);
    } else {
      const checkedAt = quiet ? new Date().toLocaleTimeString("ru-RU") : "";
      show(views.doneView({ ...stats, info: data, checkedAt, onRefresh: () => loadNext(true) }));
    }
  } catch (error) {
    showFailure(error);
  }
}

const draftKey = (task) => `vt_draft_${task.card_id}_${task.task_type}`;

function readDraft(task) {
  try {
    return localStorage.getItem(draftKey(task)) || "";
  } catch {
    return "";
  }
}

function writeDraft(task, text) {
  try {
    if (text) {
      localStorage.setItem(draftKey(task), text);
    } else {
      localStorage.removeItem(draftKey(task));
    }
  } catch {
    // без localStorage ответ сохраняется только пока открыта страница
  }
}

function showTask(task, remaining) {
  const view = views.taskView(task, remaining, {
    draft: readDraft(task),
    onDraft: (text) => writeDraft(task, text),
    onSubmit: (answer) => submit(task, view, answer),
  });
  show(view.node);
}

async function submit(task, view, answer) {
  view.setBusy(true);
  try {
    const result = await api.answer({
      card_id: task.card_id,
      task_type: task.task_type,
      answer,
      task_id: task.task_id ?? null,
      context: task.context ?? null,
    });
    writeDraft(task, "");
    stats.answered += 1;
    if (result.correct) {
      stats.correct += 1;
    }
    const feedback = views.feedbackView(result, answer, { onNext: () => loadNext() });
    show(feedback.node);
    feedback.focus();
  } catch (error) {
    view.setBusy(false);
    if (error.status === 401) {
      unauthorized();
    } else if (error.status === 503) {
      view.showError("Не удалось проверить ответ, он не записан. Ваш текст сохранен, нажмите «Ответить» еще раз.");
    } else if (error.status === 0) {
      view.showError("Нет соединения. Ваш ответ сохранен, попробуйте еще раз.");
    } else {
      view.showError(error.message);
    }
  }
}
