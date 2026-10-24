// Blocking, same-origin bootstrap: apply the saved choice before the stylesheet paints.
(() => {
  let theme = 'auto';
  try { theme = localStorage.getItem('landrop.theme') ?? 'auto'; } catch { /* Use system appearance. */ }
  const windowTheme = document.documentElement.dataset.windowTheme;
  if (windowTheme === 'auto' || windowTheme === 'light' || windowTheme === 'dark') theme = windowTheme;
  document.documentElement.dataset.theme = theme === 'dark' || (theme !== 'light' && matchMedia('(prefers-color-scheme: dark)').matches) ? 'dark' : 'light';
})();
