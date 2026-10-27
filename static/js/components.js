import { el, svg } from "./dom.js";
import { ICONS } from "./icons.js";

export function icon(name, size = 24) {
  const parts = (ICONS[name] || []).map(([tag, attrs]) => svg(tag, attrs));
  return svg(
    "svg",
    {
      viewBox: "0 0 24 24",
      width: size,
      height: size,
      fill: "none",
      stroke: "currentColor",
      "stroke-width": 2,
      "stroke-linecap": "round",
      "stroke-linejoin": "round",
      "aria-hidden": "true",
      focusable: "false",
    },
    parts,
  );
}

export function skeleton(label) {
  return el(
    "section",
    { className: "card", "aria-busy": "true" },
    el("p", { className: "visually-hidden", role: "status" }, label),
    el(
      "div",
      { className: "skeleton", "aria-hidden": "true" },
      el("div", { className: "skeleton-line title" }),
      el("div", { className: "skeleton-line" }),
      el("div", { className: "skeleton-line short" }),
      el("div", { className: "skeleton-block" }),
      el("div", { className: "skeleton-block" }),
    ),
  );
}

export function emptyBlock({ iconName = "inbox", title, text, action = null, error = false }) {
  return el(
    "div",
    { className: error ? "empty error" : "empty" },
    icon(iconName, 52),
    el("h2", {}, title),
    text && el("p", {}, text),
    action && el("button", { type: "button", className: "primary", onclick: action.onClick }, action.label),
  );
}

export function emptyState(options) {
  return el("section", { className: "card" }, emptyBlock(options));
}

function openDialog(build) {
  return new Promise((resolve) => {
    const dialog = el("dialog", { className: "modal", "aria-labelledby": "modal-title" });
    const close = (value) => {
      dialog.close();
      dialog.remove();
      resolve(value);
    };
    dialog.append(build(close));
    dialog.addEventListener("cancel", (event) => {
      event.preventDefault();
      close(null);
    });
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) {
        close(null);
      }
    });
    document.body.append(dialog);
    dialog.showModal();
  });
}

export function confirmDialog(text, { title = "Подтвердите действие", confirmText = "Да", danger = false } = {}) {
  return openDialog((close) => {
    const ok = el("button", { type: "button", className: danger ? "danger" : "primary", onclick: () => close(true) }, confirmText);
    queueMicrotask(() => ok.focus());
    return el(
      "div",
      { className: "modal-card" },
      el("h2", { id: "modal-title" }, title),
      el("p", {}, text),
      el("div", { className: "modal-actions" }, el("button", { type: "button", onclick: () => close(false) }, "Отмена"), ok),
    );
  }).then((value) => value === true);
}

export function promptDialog(title, value = "", { confirmText = "Сохранить" } = {}) {
  return openDialog((close) => {
    const input = el("input", { id: "modal-input", type: "text", maxlength: 100, "aria-label": title });
    input.value = value;
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        close(input.value.trim());
      }
    });
    queueMicrotask(() => {
      input.focus();
      input.select();
    });
    return el(
      "div",
      { className: "modal-card" },
      el("h2", { id: "modal-title" }, title),
      input,
      el(
        "div",
        { className: "modal-actions" },
        el("button", { type: "button", onclick: () => close(null) }, "Отмена"),
        el("button", { type: "button", className: "primary", onclick: () => close(input.value.trim()) }, confirmText),
      ),
    );
  });
}

let toastBox = null;

export function toast(text, kind = "ok") {
  if (!toastBox) {
    toastBox = el("div", { className: "toasts", role: "status", "aria-live": "polite" });
    document.body.append(toastBox);
  }
  const node = el("div", { className: `toast ${kind}` }, icon(kind === "ok" ? "circle-check" : "circle-alert", 22), el("span", {}, text));
  toastBox.append(node);
  setTimeout(() => node.remove(), 4000);
}
