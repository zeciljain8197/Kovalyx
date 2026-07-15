export const THEME_STORAGE_KEY = 'kovalyx-theme'

// Inline, blocking script injected as the first thing in <head> so the
// stored theme preference is applied before first paint — otherwise the
// page always flashes dark (the SSR default) before React hydrates and
// corrects it.
export const NO_FLASH_THEME_SCRIPT = `
(function () {
  try {
    if (localStorage.getItem('${THEME_STORAGE_KEY}') === 'light') {
      document.documentElement.classList.remove('dark');
    }
  } catch (e) {}
})();
`
