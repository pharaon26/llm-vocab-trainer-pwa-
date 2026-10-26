import { svg } from "./dom.js";

function truncate(text, max) {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

export function barChart(ariaLabel, rows) {
  const width = 400;
  const rowHeight = 50;
  const chart = svg("svg", { className: "chart", viewBox: `0 0 ${width} ${rows.length * rowHeight + 4}`, role: "img", "aria-label": ariaLabel });
  rows.forEach((row, index) => {
    const y = index * rowHeight;
    const fill = row.value > 0 ? Math.max(2, row.value * width) : 0;
    chart.append(
      svg("text", { x: 0, y: y + 18 }, truncate(row.label, 24), svg("tspan", { dx: 10, className: "value" }, row.text)),
      svg("rect", { x: 0, y: y + 26, width, height: 16, rx: 4, className: "track" }),
      svg("rect", { x: 0, y: y + 26, width: fill, height: 16, rx: 4, className: "fill" }),
    );
  });
  return chart;
}
