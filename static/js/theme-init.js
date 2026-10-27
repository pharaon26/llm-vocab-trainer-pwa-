try {
  const saved = localStorage.getItem("vt_theme");
  if (saved === "light" || saved === "dark") {
    document.documentElement.setAttribute("data-theme", saved);
  }
} catch {
  // без localStorage тема следует настройке системы
}
