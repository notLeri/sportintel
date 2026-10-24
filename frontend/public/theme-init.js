// Тема и палитра до первой отрисовки (без мигания). Отдельный файл: CSP запрещает inline-скрипты.
// Логика совпадает с src/shared/lib/theme.ts.
/* global localStorage, matchMedia, document */
(function () {
  var pref = "system";
  try {
    pref = localStorage.getItem("theme") || "system";
  } catch {
    // нет доступа к localStorage — тема по системе
  }
  var palette = "pitch";
  try {
    palette = localStorage.getItem("palette") || "pitch";
  } catch {
    // нет доступа — палитра по умолчанию
  }
  document.documentElement.dataset.palette = palette;
  var dark =
    pref === "dark" || (pref === "system" && matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.classList.toggle("dark", dark);
})();
