import * as api from "./api.js";
import { show, unauthorized } from "./ui.js";
import * as views from "./views.js";

const failureView = (title, error, retry) =>
  error.status === 0
    ? views.messageView("Нет соединения", "Проверьте интернет и повторите. Ваши ответы не потеряны.", "Повторить", retry, "wifi-off", true)
    : views.messageView(title, error.message, "Повторить", retry, "circle-alert", true);

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
  show(failureView("Не удалось загрузить задание", error, () => loadNext()));
}

async function loadNext(quiet = false) {
  if (!quiet) {
    show(views.loadingView("Готовим задание…"));
  }
  try {
    const data = await api.nextTask();
    if (data.task) {
      showTask(data.task, `В очереди: ${data.remaining}`, false, { value: stats.answered, max: stats.answered + data.remaining });
    } else {
      const checkedAt = quiet ? new Date().toLocaleTimeString("ru-RU") : "";
      show(
        views.doneView({
          ...stats,
          info: data,
          checkedAt,
          onRefresh: () => loadNext(true),
          onPractice: () => loadPractice(),
        }),
      );
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

function showTask(task, meta, practice = false, progress = null) {
  const view = views.taskView(task, meta, {
    progress,
    draft: readDraft(task),
    onDraft: (text) => writeDraft(task, text),
    onSubmit: (answer) => submit(task, view, answer, practice),
    onExit: practice ? () => loadNext() : null,
  });
  show(view.node);
}

async function loadPractice(previousCardId = null) {
  show(views.loadingView("Подбираем задание…"));
  try {
    const { task } = await api.practiceNext(previousCardId);
    if (task) {
      showTask(task, "Свободная тренировка: расписание повторений не меняется", true);
    } else {
      show(views.messageView("Пока нечего тренировать", "Сначала откройте новые термины в повторении.", "К повторению", () => loadNext()));
    }
  } catch (error) {
    if (error.status === 409) {
      show(views.messageView("Сначала завершите повторение", "Свободная тренировка доступна, когда задания на сегодня выполнены.", "К повторению", () => loadNext()));
    } else {
      showFailure(error);
    }
  }
}

async function submit(task, view, answer, practice) {
  view.setBusy(true);
  try {
    const send = practice ? api.practiceAnswer : api.answer;
    const result = await send({
      card_id: task.card_id,
      task_type: task.task_type,
      answer,
      task_id: task.task_id ?? null,
      context: task.context ?? null,
    });
    writeDraft(task, "");
    if (!practice) {
      stats.answered += 1;
      if (result.correct) {
        stats.correct += 1;
      }
    }
    const feedback = views.feedbackView(result, answer, {
      onNext: () => (practice ? loadPractice(task.card_id) : loadNext()),
      onExit: practice ? () => loadNext() : null,
    });
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
