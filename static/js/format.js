const DAY = 86400000;

function startOfToday() {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return today;
}

export function describeDate(isoDate) {
  const date = new Date(`${isoDate}T00:00:00`);
  const days = Math.round((date - startOfToday()) / DAY);
  const formatted = date.toLocaleDateString("ru-RU", { day: "numeric", month: "long" });
  if (days === 0) {
    return "сегодня";
  }
  if (days === 1) {
    return "завтра";
  }
  if (days < 0) {
    return `просрочено (${formatted})`;
  }
  return formatted;
}
