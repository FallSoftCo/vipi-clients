(() => {
  const section = document.getElementById('languages');
  if (!section) return;

  const preview = section.querySelector('.language-preview');
  const grid = preview.querySelector('.language-grid');
  const toggle = section.querySelector('.language-rotation');
  const catalog = section.querySelector('.language-catalog');
  const languages = [...catalog.querySelectorAll('[data-language]')];
  const tilesPerPage = 8;
  const interval = 5500;
  const pageCount = Math.ceil(languages.length / tilesPerPage);
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
  let page = 0;
  let inView = false;
  let paused = false;
  let timer = 0;

  function showPage() {
    const start = page * tilesPerPage;
    const items = Array.from({ length: tilesPerPage }, (_, index) =>
      languages[(start + index) % languages.length].cloneNode(true));
    grid.replaceChildren(...items);
  }

  function shouldRotate() {
    return inView && !paused && !document.hidden && !catalog.open && !reducedMotion.matches;
  }

  function schedule() {
    clearTimeout(timer);
    toggle.hidden = reducedMotion.matches;
    if (!shouldRotate()) return;
    timer = setTimeout(() => {
      if (!shouldRotate()) return;
      page = (page + 1) % pageCount;
      showPage();
      for (const label of grid.querySelectorAll('span, small')) {
        label.animate([{ opacity: 0.35 }, { opacity: 1 }], { duration: 280, easing: 'ease-out' });
      }
      schedule();
    }, interval);
  }

  toggle.addEventListener('click', () => {
    paused = !paused;
    toggle.textContent = paused ? 'Resume rotation' : 'Pause rotation';
    schedule();
  });
  catalog.addEventListener('toggle', schedule);
  document.addEventListener('visibilitychange', schedule);
  reducedMotion.addEventListener('change', schedule);
  showPage();
  preview.hidden = false;
  new IntersectionObserver(([entry]) => {
    inView = entry.intersectionRatio >= 0.35;
    schedule();
  }, { threshold: 0.35 }).observe(grid);
})();
