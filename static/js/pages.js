import * as api from "./api.js";
import * as pageViews from "./page-views.js";
import { show, unauthorized } from "./ui.js";
import * as views from "./views.js";

function failure(error, retry) {
  if (error.status === 401) {
    unauthorized();
    return;
  }
  show(views.messageView("Не удалось загрузить данные", error.message, "Повторить", retry));
}

export async function showProgress() {
  show(views.loadingView("Загружаем прогресс…"));
  try {
    const data = await api.progress();
    let filter = "all";
    const render = () =>
      show(
        pageViews.progressView({
          data,
          filter,
          onFilter: (value) => {
            filter = value;
            render();
          },
        }),
      );
    render();
  } catch (error) {
    failure(error, showProgress);
  }
}

const HISTORY_PAGE = 30;

export async function showHistory() {
  let term = "";
  let items = [];
  let total = 0;
  let terms = [];

  async function load(reset) {
    const offset = reset ? 0 : items.length;
    const query = `?limit=${HISTORY_PAGE}&offset=${offset}${term ? `&term=${encodeURIComponent(term)}` : ""}`;
    const data = await api.history(query);
    items = reset ? data.items : items.concat(data.items);
    total = data.total;
    terms = data.terms;
  }

  const render = () =>
    show(
      pageViews.historyView({
        terms,
        term,
        items,
        total,
        onTerm: (value) => {
          term = value;
          guard(() => load(true));
        },
        onMore: () => guard(() => load(false)),
      }),
    );

  async function guard(action) {
    try {
      await action();
      render();
    } catch (error) {
      failure(error, showHistory);
    }
  }

  show(views.loadingView("Загружаем историю…"));
  await guard(() => load(true));
}

export async function showDictionary() {
  show(views.loadingView("Загружаем словарь…"));
  try {
    show(pageViews.dictionaryView({ entries: await api.dictionary() }));
  } catch (error) {
    failure(error, showDictionary);
  }
}

export async function showStats() {
  show(views.loadingView("Загружаем статистику…"));
  try {
    show(pageViews.statsView({ data: await api.stats() }));
  } catch (error) {
    failure(error, showStats);
  }
}

export async function showSettings(notice = "") {
  show(views.loadingView("Загружаем настройки…"));
  try {
    const settings = await api.settings();
    const render = (message, error) =>
      show(
        pageViews.settingsView({
          settings,
          notice: message,
          error,
          onSave: async (value) => {
            try {
              Object.assign(settings, await api.saveSettings(value));
              render(`Сохранено: ${settings.new_cards_per_day} в день.`, "");
            } catch (err) {
              if (err.status === 401) {
                unauthorized();
              } else {
                render("", err.message);
              }
            }
          },
        }),
      );
    render(notice, "");
  } catch (error) {
    failure(error, showSettings);
  }
}
