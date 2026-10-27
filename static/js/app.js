import * as api from "./api.js";
import { clear, el, svg } from "./dom.js";
import { showHistory, showProgress, showSettings, showStats } from "./pages.js";
import { resetStats, showStart } from "./session.js";
import { setLogoutHandler, show } from "./ui.js";
import * as views from "./views.js";
import { showDictionary } from "./words.js";

const userBox = document.getElementById("user-box");
const nav = document.getElementById("nav");

const NAV = [
  ["session", "Повторение", "M5 4h14a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1z M8 9h8 M8 13h5", showStart],
  ["progress", "Прогресс", "M5 20v-6 M12 20V8 M19 20V4", showProgress],
  ["dictionary", "Словарь", "M5 4h11a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3z M5 17a3 3 0 0 1 3-3h11", showDictionary],
  ["history", "История", "M12 3a9 9 0 1 0 0 18a9 9 0 0 0 0-18z M12 7v5l3 2", showHistory],
  ["stats", "Статистика", "M12 3a9 9 0 1 0 0 18a9 9 0 0 0 0-18z M12 3v9h9", showStats],
];

const ROUTES = { ...Object.fromEntries(NAV.map(([id, , , handler]) => [id, handler])), settings: showSettings };

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
  if (!api.getName()) {
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
    userBox.append(
      el("span", {}, name),
      " ",
      el("a", { href: "#/settings" }, "Настройки"),
      " ",
      el("button", { type: "button", className: "link", onclick: () => logout() }, "Выйти"),
    );
  }
}

function logout(message = "") {
  api.logout();
  resetStats();
  renderUserBox();
  setNavVisible(false);
  showLogin("", message);
}

async function authenticate(name, action, showForm) {
  try {
    const me = await action();
    if (me.role !== "student") {
      location.assign("/teacher.html");
      return;
    }
    renderUserBox();
    go("session");
  } catch (err) {
    showForm(name, err.message);
  }
}

function showLogin(name = "", error = "") {
  show(
    views.loginView({
      name,
      error,
      onSubmit: (value, password) => authenticate(value, () => api.login(value, { password }), showLogin),
      onShowRegister: (value) => showRegister(value),
    }),
  );
}

function showRegister(name = "", error = "") {
  show(
    views.registerView({
      name,
      error,
      onSubmit: (value, password, confirm, role) =>
        authenticate(value, () => api.register(value, password, confirm, role), showRegister),
      onShowLogin: (value) => showLogin(value),
    }),
  );
}

async function init() {
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  }
  setLogoutHandler(logout);
  window.addEventListener("hashchange", route);
  try {
    const me = await api.me();
    if (me.role !== "student") {
      location.assign("/teacher.html");
      return;
    }
  } catch (error) {
    if (error.status === 401) {
      setNavVisible(false);
      showLogin();
      return;
    }
  }
  renderUserBox();
  route();
}

init();
