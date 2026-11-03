const motionPreference = matchMedia('(prefers-reduced-motion: reduce)');
let codeObserver: IntersectionObserver | undefined;
let explorerScroll: { x: number; y: number; layoutTop: number; repoChanged: boolean } | null = null;

function updateExternalLinks() {
  document.querySelectorAll<HTMLAnchorElement>('a[href]').forEach((link) => {
    if ((link.protocol !== 'http:' && link.protocol !== 'https:') || link.origin === location.origin) return;
    link.target = '_blank';
    link.rel = [...new Set([...link.rel.split(/\s+/).filter(Boolean), 'noopener', 'noreferrer'])].join(' ');
  });
}

function closeNavigationMenu(event: MouseEvent) {
  if (event.target instanceof Element && event.target.closest('.nav-menu')) return;
  document.querySelector<HTMLDetailsElement>('.nav-menu[open]')?.removeAttribute('open');
}

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
  updateExternalLinks();
  setupCodePreviews();
});

document.addEventListener('astro:before-swap', (event) => {
  event.newDocument.documentElement.dataset.theme = document.documentElement.dataset.theme;
  event.newDocument.documentElement.classList.add('js-motion');
  event.newDocument.documentElement.dataset.routeMotion = isGuideLanguageSwitch(event.from, event.to) ? 'none' : 'fade';

  const current = document.querySelector<HTMLElement>('main[data-explorer]');
  const next = event.newDocument.querySelector<HTMLElement>('main[data-explorer]');
  const currentIntro = current?.querySelector<HTMLElement>('.explorer-intro');
  const nextIntro = next?.querySelector<HTMLElement>('.explorer-intro');
  const currentSidebar = current?.querySelector<HTMLElement>('.explorer-sidebar');
  const nextSidebar = next?.querySelector<HTMLElement>('.explorer-sidebar');
  const currentArticle = current?.querySelector<HTMLElement>('.explorer-content');
  const nextArticle = next?.querySelector<HTMLElement>('.explorer-content');
  if (!current || !next || !currentIntro || !nextIntro || !currentSidebar || !nextSidebar || !currentArticle || !nextArticle) return;

  const layout = current.querySelector<HTMLElement>('.explorer-layout');
  explorerScroll = event.navigationType === 'traverse' || !layout ? null : {
    x: scrollX,
    y: scrollY,
    layoutTop: layout.getBoundingClientRect().top + scrollY,
    repoChanged: current.dataset.repo !== next.dataset.repo,
  };
  document.documentElement.dataset.routeMotion = 'none';
  event.swap = () => {
    document.title = event.newDocument.title;
    for (const selector of ['link[rel="canonical"]', 'meta[name="description"]', 'meta[property="og:url"]', 'meta[property="og:title"]', 'meta[property="og:description"]']) {
      const oldTag = document.head.querySelector(selector);
      const newTag = event.newDocument.head.querySelector(selector);
      if (oldTag && newTag) oldTag.replaceWith(newTag);
    }
    if (current.dataset.repo !== next.dataset.repo) {
      const oldIsland = currentSidebar.closest('astro-island');
      const newIsland = nextSidebar.closest('astro-island');
      if (oldIsland && newIsland) oldIsland.replaceWith(newIsland);
      currentIntro.replaceWith(nextIntro);
    }
    currentArticle.replaceWith(nextArticle);
    current.dataset.repo = next.dataset.repo;
  };
});

document.addEventListener('astro:after-swap', () => {
  if (explorerScroll) {
    const headerHeight = document.querySelector<HTMLElement>('.site-header')?.offsetHeight ?? 60;
    const mobileTarget = document.querySelector<HTMLElement>(explorerScroll.repoChanged ? '.explorer-sidebar' : '.explorer-content');
    const fileTop = Math.max(0, explorerScroll.layoutTop - headerHeight - 16);
    const mobileTop = mobileTarget ? Math.max(0, mobileTarget.getBoundingClientRect().top + scrollY - headerHeight - 16) : fileTop;
    const top = matchMedia('(max-width: 850px)').matches ? mobileTop : Math.min(explorerScroll.y, fileTop);
    scrollTo({ left: explorerScroll.x, top, behavior: 'instant' });
  }
  explorerScroll = null;
});

window.addEventListener('scroll', updateHeader, { passive: true });

document.addEventListener('click', (event) => {
  closeNavigationMenu(event);
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
