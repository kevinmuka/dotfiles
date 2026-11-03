const motionPreference = matchMedia('(prefers-reduced-motion: reduce)');
let revealObserver: IntersectionObserver | undefined;

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

function setupReveals() {
  revealObserver?.disconnect();
  if (motionPreference.matches || !('IntersectionObserver' in window)) return;
  const targets = document.querySelectorAll<HTMLElement>('.hero-copy, .terminal, .page-hero, .section-head, .card, .flow-step, .panel:not(.explorer-content):not(.explorer-sidebar), .stack-row, .doc-intro, .explorer-intro');
  revealObserver = new IntersectionObserver((entries, observer) => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;
      entry.target.classList.add('is-visible');
      observer.unobserve(entry.target);
    }
  }, { threshold: 0.08, rootMargin: '0px 0px 24px 0px' });
  targets.forEach((target, index) => {
    target.classList.add('reveal-ready');
    target.style.setProperty('--reveal-delay', `${Math.min(index % 4, 3) * 65}ms`);
    revealObserver?.observe(target);
  });
}

document.addEventListener('astro:page-load', () => {
  updateHeader();
  updateThemeButton();
  setupReveals();
});

document.addEventListener('astro:before-swap', (event) => {
  event.newDocument.documentElement.dataset.theme = document.documentElement.dataset.theme;
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
  if (!motionPreference.matches && document.startViewTransition) document.startViewTransition(apply);
  else apply();
});
