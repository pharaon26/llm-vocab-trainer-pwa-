import { icon } from "./components.js";
import { el } from "./dom.js";

const root = document.documentElement;
const query = window.matchMedia("(prefers-color-scheme: dark)");

const current = () => root.getAttribute("data-theme") || (query.matches ? "dark" : "light");

export function themeToggle() {
  const button = el("button", { type: "button", className: "icon-button" });
  const render = () => {
    const dark = current() === "dark";
    button.replaceChildren(icon(dark ? "sun" : "moon", 20));
    button.setAttribute("aria-label", dark ? "Включить светлую тему" : "Включить тёмную тему");
    button.title = button.getAttribute("aria-label");
  };
  button.addEventListener("click", () => {
    const next = current() === "dark" ? "light" : "dark";
    root.setAttribute("data-theme", next);
    try {
      localStorage.setItem("vt_theme", next);
    } catch {
      // выбор темы просто не запомнится
    }
    render();
  });
  query.addEventListener("change", render);
  render();
  return button;
}
