const motionPreference = matchMedia('(prefers-reduced-motion: reduce)');
let codeObserver: IntersectionObserver | undefined;

function updateHeader() {
  document.querySelector('.site-header')?.classList.toggle('is-compact', scrollY > 48);
}

function updateThemeButton() {
  const button = document.querySelector<HTMLButtonElement>('[data-theme-toggle]');
  if (!button) return;
  const dark = document.documentElement.dataset.theme === 'dark';
  button.setAttribute('aria-label', dark ? 'Switch to light theme' : 'Switch to dark theme');
  button.setAttribute('title', dark ? 'Switch to light theme' : 'Switch to dark theme');
  const icon = button.querySelector('[data-theme-icon]');
  if (icon) icon.textContent = dark ? '☀' : '☾';
}

function setupCodePreviews() {
  codeObserver?.disconnect();
  if (motionPreference.matches || !('IntersectionObserver' in window)) {
    document.querySelectorAll<HTMLElement>('.code-window').forEach((window) => window.classList.add('is-code-playing'));
    return;
  }
  codeObserver = new IntersectionObserver((entries, observer) => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;
      entry.target.classList.add('is-code-playing');
      observer.unobserve(entry.target);
    }
  }, { threshold: 0.15 });
  document.querySelectorAll<HTMLElement>('.code-window').forEach((window) => {
    const code = window.querySelector('pre');
    if (!code) return;
    const lines = code.textContent?.trimEnd().split('\n').length ?? 8;
    window.style.setProperty('--code-lines', String(lines));
    window.style.setProperty('--code-duration', `${Math.min(1.8, Math.max(0.7, lines * 0.12))}s`);
    codeObserver?.observe(window);
  });
}

function isGuideLanguageSwitch(from: URL, to: URL) {
  const guide = /^\/(macbackup|nvim)\/docs(?:\/it)?\/?$/;
  const normalize = (path: string) => path.replace(/\/it\/?$/, '').replace(/\/$/, '');
  return from.pathname !== to.pathname && guide.test(from.pathname) && guide.test(to.pathname)
    && normalize(from.pathname) === normalize(to.pathname);
}

document.addEventListener('astro:page-load', () => {
  updateHeader();
  updateThemeButton();
  setupCodePreviews();
});

document.addEventListener('astro:before-swap', (event) => {
  event.newDocument.documentElement.dataset.theme = document.documentElement.dataset.theme;
  event.newDocument.documentElement.classList.add('js-motion');
  event.newDocument.documentElement.dataset.routeMotion = isGuideLanguageSwitch(event.from, event.to) ? 'none' : 'fade';
});

window.addEventListener('scroll', updateHeader, { passive: true });

document.addEventListener('click', (event) => {
  const target = event.target;
  if (!(target instanceof Element)) return;
  const button = target.closest<HTMLButtonElement>('[data-theme-toggle]');
  if (!button) return;
  const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
  const apply = () => {
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem('dotfiles-theme', next); } catch { /* Storage may be unavailable. */ }
    updateThemeButton();
  };
  document.documentElement.classList.add('theme-switching');
  apply();
  requestAnimationFrame(() => requestAnimationFrame(() => {
    document.documentElement.classList.remove('theme-switching');
  }));
});
