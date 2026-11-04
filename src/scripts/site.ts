const motionPreference = matchMedia('(prefers-reduced-motion: reduce)');
const mobileHeader = matchMedia('(max-width: 620px)');

// On a full reload, let the browser restore the exact current position before
// ClientRouter runs. Firefox needs this change before pagehide.
window.addEventListener('beforeunload', () => {
  history.scrollRestoration = 'auto';
  if (history.state && typeof history.state === 'object' && 'index' in history.state) {
    history.replaceState({ ...history.state, scrollX, scrollY }, '');
  }
});
window.addEventListener('pageshow', (event) => {
  if (event.persisted) history.scrollRestoration = 'manual';
});

let codeObserver: IntersectionObserver | undefined;
let explorerScroll: { x: number; y: number; layoutTop: number; repoChanged: boolean } | null = null;
let guideScroll: { x: number; y: number; headingId?: string; headingTop?: number } | null = null;
let explorerLoadingTimer: number | undefined;
let explorerLoadingGeneration = 0;
let pageLoadingTimer: number | undefined;
let pageLoadingGeneration = 0;

function stopPageLoading() {
  pageLoadingGeneration++;
  clearTimeout(pageLoadingTimer);
  document.querySelector<HTMLElement>('.site-header.is-page-loading')?.classList.remove('is-page-loading');
}

function stopExplorerLoading() {
  explorerLoadingGeneration++;
  clearTimeout(explorerLoadingTimer);
  document.querySelector<HTMLElement>('.explorer-content.is-loading')?.classList.remove('is-loading');
}

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
  document.querySelector('.site-header')?.classList.toggle('is-compact', !mobileHeader.matches && scrollY > 48);
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

function updateThemeColor() {
  document.querySelector<HTMLMetaElement>('meta[name="theme-color"]')?.setAttribute(
    'content', document.documentElement.dataset.theme === 'dark' ? '#0e1725' : '#f6f8fc',
  );
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

function updatePageMetadata(nextDocument: Document) {
  document.title = nextDocument.title;
  document.documentElement.lang = nextDocument.documentElement.lang;
  for (const selector of ['link[rel="canonical"]', 'meta[name="description"]', 'meta[property="og:url"]', 'meta[property="og:title"]', 'meta[property="og:description"]']) {
    const oldTag = document.head.querySelector(selector);
    const newTag = nextDocument.head.querySelector(selector);
    if (oldTag && newTag) oldTag.replaceWith(newTag);
  }
}

document.addEventListener('astro:page-load', () => {
  stopPageLoading();
  updateHeader();
  updateThemeButton();
  updateThemeColor();
  updateExternalLinks();
  setupCodePreviews();
});

document.addEventListener('astro:before-preparation', (event) => {
  stopPageLoading();
  const internalExplorerNavigation = /^\/explore\/(dotfiles|nvim)(?:\/|$)/.test(event.from.pathname)
    && /^\/explore\/(dotfiles|nvim)(?:\/|$)/.test(event.to.pathname);
  if (!internalExplorerNavigation) {
    const generation = pageLoadingGeneration;
    pageLoadingTimer = window.setTimeout(() => {
      if (generation !== pageLoadingGeneration) return;
      document.querySelector<HTMLElement>('.site-header')?.classList.add('is-page-loading');
    }, 220);
    event.signal.addEventListener('abort', () => {
      if (generation === pageLoadingGeneration) stopPageLoading();
    }, { once: true });
  }
  stopExplorerLoading();
  const current = document.querySelector<HTMLElement>('main[data-explorer]');
  const destinationRepo = /^\/explore\/(dotfiles|nvim)(?:\/|$)/.exec(event.to.pathname)?.[1];
  if (!current || !destinationRepo) return;
  const generation = explorerLoadingGeneration;
  explorerLoadingTimer = window.setTimeout(() => {
    if (generation !== explorerLoadingGeneration) return;
    const article = current.querySelector<HTMLElement>('.explorer-content');
    const label = article?.querySelector<HTMLElement>('[data-explorer-loading-text]');
    if (label) label.textContent = current.dataset.repo === destinationRepo ? 'Opening file…' : 'Switching repository…';
    article?.classList.add('is-loading');
  }, 180);
  event.signal.addEventListener('abort', () => {
    if (generation === explorerLoadingGeneration) stopExplorerLoading();
  }, { once: true });
});

document.addEventListener('astro:after-preparation', stopPageLoading);

document.addEventListener('astro:before-swap', (event) => {
  stopExplorerLoading();
  event.newDocument.documentElement.dataset.theme = document.documentElement.dataset.theme;
  event.newDocument.querySelector('meta[name="theme-color"]')?.setAttribute('content', document.documentElement.dataset.theme === 'dark' ? '#0e1725' : '#f6f8fc');
  event.newDocument.documentElement.classList.add('js-motion');
  const guideSwitch = isGuideLanguageSwitch(event.from, event.to);
  event.newDocument.documentElement.dataset.routeMotion = guideSwitch ? 'none' : 'fade';

  const currentGuide = guideSwitch ? document.querySelector<HTMLElement>('main[data-guide]') : null;
  const nextGuide = guideSwitch ? event.newDocument.querySelector<HTMLElement>('main[data-guide]') : null;
  const currentGuideIntro = currentGuide?.querySelector<HTMLElement>('.doc-intro');
  const nextGuideIntro = nextGuide?.querySelector<HTMLElement>('.doc-intro');
  const currentGuideLayout = currentGuide?.querySelector<HTMLElement>('.document-layout');
  const nextGuideLayout = nextGuide?.querySelector<HTMLElement>('.document-layout');
  const currentLanguageSwitch = currentGuideIntro?.querySelector<HTMLElement>('.language-switch');
  const nextLanguageSwitch = nextGuideIntro?.querySelector<HTMLElement>('.language-switch');
  const currentIntroContent = [...currentGuideIntro?.children ?? []].filter((child) => child !== currentLanguageSwitch);
  const nextIntroContent = [...nextGuideIntro?.children ?? []].filter((child) => child !== nextLanguageSwitch);
  if (currentGuideIntro && nextGuideIntro && currentGuideLayout && nextGuideLayout && currentLanguageSwitch && nextLanguageSwitch && currentIntroContent.length === nextIntroContent.length) {
    const heading = [...currentGuideLayout.querySelectorAll<HTMLElement>('.doc-content :is(h1,h2,h3,h4,h5,h6)[id]')]
      .filter((item) => item.getBoundingClientRect().top <= 120).at(-1);
    guideScroll = event.navigationType === 'traverse' ? null : {
      x: scrollX,
      y: scrollY,
      headingId: heading?.id,
      headingTop: heading?.getBoundingClientRect().top,
    };
    document.documentElement.dataset.routeMotion = 'none';
    event.swap = () => {
      updatePageMetadata(event.newDocument);
      currentIntroContent.forEach((oldChild, index) => {
        const newChild = nextIntroContent[index];
        newChild.classList.add('guide-enter');
        oldChild.replaceWith(newChild);
      });
      currentLanguageSwitch.setAttribute('aria-label', nextLanguageSwitch.getAttribute('aria-label') || 'Guide language');
      for (const link of currentLanguageSwitch.querySelectorAll<HTMLAnchorElement>('a[lang]')) {
        if (link.lang === event.newDocument.documentElement.lang) link.setAttribute('aria-current', 'page');
        else link.removeAttribute('aria-current');
      }
      nextGuideLayout.classList.add('guide-enter');
      currentGuideLayout.replaceWith(nextGuideLayout);
    };
    return;
  }

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
    updatePageMetadata(event.newDocument);
    if (current.dataset.repo !== next.dataset.repo) {
      const oldIsland = currentSidebar.closest('astro-island');
      const newIsland = nextSidebar.closest('astro-island');
      if (oldIsland && newIsland) {
        newIsland.classList.add('explorer-enter');
        oldIsland.replaceWith(newIsland);
      }
      nextIntro.classList.add('explorer-enter');
      currentIntro.replaceWith(nextIntro);
    }
    nextArticle.classList.add('explorer-enter');
    currentArticle.replaceWith(nextArticle);
    current.dataset.repo = next.dataset.repo;
  };
});

document.addEventListener('astro:after-swap', () => {
  if (guideScroll) {
    const heading = guideScroll.headingId ? document.getElementById(guideScroll.headingId) : null;
    const top = heading && guideScroll.headingTop !== undefined
      ? scrollY + heading.getBoundingClientRect().top - guideScroll.headingTop
      : guideScroll.y;
    scrollTo({ left: guideScroll.x, top, behavior: 'instant' });
  }
  guideScroll = null;
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
mobileHeader.addEventListener('change', updateHeader);

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
    updateThemeColor();
  };
  document.documentElement.classList.add('theme-switching');
  apply();
  requestAnimationFrame(() => requestAnimationFrame(() => {
    document.documentElement.classList.remove('theme-switching');
  }));
});
