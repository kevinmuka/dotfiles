(() => {
  const header = document.querySelector('.site-header');
  if (!header) return;

  const update = () => header.classList.toggle('is-compact', window.scrollY > 48);
  window.addEventListener('scroll', update, { passive: true });
  update();

  const journey = document.querySelector('.link-journey');
  if (journey) {
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
    journey.addEventListener('click', (event) => {
      if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || reducedMotion.matches) return;
      event.preventDefault();
      if (journey.classList.contains('is-departing')) return;
      journey.classList.add('is-departing');
      window.setTimeout(() => window.location.assign(journey.href), 330);
    });
    window.addEventListener('pageshow', () => journey.classList.remove('is-departing'));
  }
})();
