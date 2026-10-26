const DAY = 86400000;

export function plural(n, one, few, many) {
  const mod100 = n % 100;
  const mod10 = n % 10;
  if (mod100 >= 11 && mod100 <= 14) {
    return many;
  }
  if (mod10 === 1) {
    return one;
  }
  return mod10 >= 2 && mod10 <= 4 ? few : many;
}

export const percent = (value) => `${Math.round(value * 100)}%`;

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
