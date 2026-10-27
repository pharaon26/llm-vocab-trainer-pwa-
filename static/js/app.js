import * as api from "./api.js";
import { icon } from "./components.js";
import { clear, el } from "./dom.js";
import { showHistory, showProgress, showSettings, showStats } from "./pages.js";
import { resetStats, showStart } from "./session.js";
import { showTeachers } from "./teachers.js";
import { themeToggle } from "./theme.js";
import { setLogoutHandler, show } from "./ui.js";
import * as views from "./views.js";
import { showDictionary } from "./words.js";

const userBox = document.getElementById("user-box");
const nav = document.getElementById("nav");

const NAV = [
  ["session", "Повторение", "layers", showStart],
  ["progress", "Прогресс", "trending-up", showProgress],
  ["dictionary", "Словарь", "book-open", showDictionary],
  ["history", "История", "history", showHistory],
  ["teachers", "Учителя", "users", showTeachers],
  ["stats", "Статистика", "chart-pie", showStats],
];

const ROUTES = { ...Object.fromEntries(NAV.map(([id, , , handler]) => [id, handler])), settings: showSettings };

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
      NAV.map(([id, label, name]) =>
        el("li", {}, el("a", { href: `#/${id}`, "aria-current": id === active ? "page" : null }, icon(name), label)),
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
  userBox.append(themeToggle());
  const name = api.getName();
  if (name) {
    userBox.append(
      el("span", { className: "user-name" }, name),
      el("a", { className: "icon-button", href: "#/settings", "aria-label": "Настройки", title: "Настройки" }, icon("settings", 20)),
      el("button", { type: "button", className: "icon-button", "aria-label": "Выйти", title: "Выйти", onclick: () => logout() }, icon("log-out", 20)),
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
      renderUserBox();
      showLogin();
      return;
    }
  }
  renderUserBox();
  route();
}

init();
