import { clear } from "./dom.js";

const root = document.getElementById("app");
let logoutHandler = () => {};

export function setLogoutHandler(handler) {
  logoutHandler = handler;
}

export function unauthorized(message = "Сессия истекла, войдите снова.") {
  logoutHandler(message);
}

export function show(node) {
  clear(root);
  root.append(node);
  const heading = root.querySelector("h2");
  if (heading) {
    heading.tabIndex = -1;
    heading.focus({ preventScroll: true });
  }
  window.scrollTo(0, 0);
}
