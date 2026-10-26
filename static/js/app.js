import * as api from "./api.js";
import { clear, el, svg } from "./dom.js";
import { showHistory, showProgress } from "./pages.js";
import { resetStats, showStart } from "./session.js";
import { setLogoutHandler, show } from "./ui.js";
import * as views from "./views.js";

const userBox = document.getElementById("user-box");
const nav = document.getElementById("nav");

const NAV = [
  ["session", "Повторение", "M5 4h14a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1z M8 9h8 M8 13h5", showStart],
  ["progress", "Прогресс", "M5 20v-6 M12 20V8 M19 20V4", showProgress],
  ["history", "История", "M12 3a9 9 0 1 0 0 18a9 9 0 0 0 0-18z M12 7v5l3 2", showHistory],
];

const ROUTES = Object.fromEntries(NAV.map(([id, , , handler]) => [id, handler]));

function icon(path) {
  return svg("svg", { viewBox: "0 0 24 24", "aria-hidden": "true" }, path.split(" M").map((part, i) => svg("path", { d: i ? `M${part}` : part })));
}

function currentRoute() {
  const name = location.hash.replace(/^#\//, "");
  return ROUTES[name] ? name : "session";
}

function renderNav(active) {
  clear(nav);
  nav.append(
    el(
      "ul",
      {},
      NAV.map(([id, label, path]) =>
        el("li", {}, el("a", { href: `#/${id}`, "aria-current": id === active ? "page" : null }, icon(path), label)),
      ),
    ),
  );
}

function setNavVisible(visible) {
  nav.hidden = !visible;
  document.body.classList.toggle("has-nav", visible);
}

function route() {
  if (!api.getToken()) {
    return;
  }
  const name = currentRoute();
  renderNav(name);
  setNavVisible(true);
  ROUTES[name]();
}

function go(name) {
  if (location.hash === `#/${name}`) {
    route();
  } else {
    location.hash = `#/${name}`;
  }
}

function renderUserBox() {
  clear(userBox);
  const name = api.getName();
  if (name) {
    userBox.append(el("span", {}, name), " ", el("button", { type: "button", className: "link", onclick: () => logout() }, "Выйти"));
  }
}

function logout(message = "") {
  api.clearSession();
  resetStats();
  renderUserBox();
  setNavVisible(false);
  showLogin("", message);
}

function showLogin(name = "", error = "") {
  show(
    views.loginView({
      name,
      error,
      onSubmit: async (value) => {
        try {
          await api.login(value);
          renderUserBox();
          go("session");
        } catch (err) {
          showLogin(value, err.message);
        }
      },
    }),
  );
}

async function init() {
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  }
  setLogoutHandler(logout);
  window.addEventListener("hashchange", route);
  renderUserBox();
  if (!api.getToken()) {
    setNavVisible(false);
    showLogin();
    return;
  }
  try {
    await api.me();
  } catch (error) {
    if (error.status === 401) {
      logout();
      return;
    }
  }
  route();
}

init();
