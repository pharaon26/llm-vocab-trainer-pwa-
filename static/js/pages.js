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
