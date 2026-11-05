(() => {
  'use strict';
  const showcase = document.querySelector('[data-promo-carousel]');
  if (!showcase) return;
  const track = showcase.querySelector('[data-promo-track]');
  const cards = [...track.querySelectorAll('.promo-ticket')];
  if (cards.length < 2) return;
  const compact = matchMedia('(max-width: 860px)');
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const controls = showcase.querySelector('[data-promo-controls]');
  const dots = showcase.querySelector('[data-promo-dots]');
  const counter = showcase.querySelector('[data-promo-count]');
  let current = 0, timer, scrollFrame, touching = false, visible = true;

  const pagination = cards.map((card, index) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.setAttribute('aria-label', `Ver promoción ${index + 1} de ${cards.length}`);
    button.setAttribute('aria-controls', track.id);
    button.addEventListener('click', () => go(index));
    dots.append(button);
    return button;
  });

  function update() {
    const left = track.getBoundingClientRect().left;
    let nearest = Infinity;
    cards.forEach((card, index) => {
      const distance = Math.abs(card.getBoundingClientRect().left - left);
      if (distance < nearest) { nearest = distance; current = index; }
    });
    pagination.forEach((button, index) => {
      if (index === current) button.setAttribute('aria-current', 'true');
      else button.removeAttribute('aria-current');
    });
    counter.textContent = `${current + 1} / ${cards.length}`;
  }

  function schedule() {
    clearTimeout(timer);
    if (!compact.matches || reduced.matches || touching || !visible || document.hidden) return;
    timer = setTimeout(() => {
      if (!document.querySelector('dialog[open]')) go(current + 1);
      else schedule();
    }, 5000);
  }

  function go(index) {
    if (!compact.matches) return;
    const target = (index + cards.length) % cards.length;
    track.scrollTo({left: cards[target].offsetLeft - cards[0].offsetLeft, behavior: reduced.matches ? 'instant' : 'smooth'});
    schedule();
  }

  function configure() {
    controls.hidden = !compact.matches;
    if (compact.matches) {
      showcase.setAttribute('aria-roledescription', 'carrusel');
      track.tabIndex = 0;
      track.setAttribute('aria-label', 'Promociones: deslizá o usá las flechas para recorrerlas');
      track.scrollTo({left: cards[current].offsetLeft - cards[0].offsetLeft, behavior: 'instant'});
    } else {
      showcase.removeAttribute('aria-roledescription');
      track.removeAttribute('tabindex');
      track.removeAttribute('aria-label');
    }
    if (compact.matches) update();
    schedule();
  }

  showcase.querySelector('[data-promo-prev]').addEventListener('click', () => go(current - 1));
  showcase.querySelector('[data-promo-next]').addEventListener('click', () => go(current + 1));
  track.addEventListener('keydown', event => {
    if (compact.matches && (event.key === 'ArrowLeft' || event.key === 'ArrowRight')) {
      event.preventDefault(); go(current + (event.key === 'ArrowRight' ? 1 : -1));
    }
  });
  track.addEventListener('scroll', () => {
    cancelAnimationFrame(scrollFrame);
    scrollFrame = requestAnimationFrame(update);
    schedule();
  }, {passive: true});
  track.addEventListener('pointerdown', () => { touching = true; schedule(); }, {passive: true});
  window.addEventListener('pointerup', () => { if (touching) { touching = false; schedule(); } }, {passive: true});
  window.addEventListener('pointercancel', () => { if (touching) { touching = false; schedule(); } }, {passive: true});
  document.addEventListener('visibilitychange', schedule);
  compact.addEventListener('change', configure);
  reduced.addEventListener('change', configure);
  if ('IntersectionObserver' in window) {
    new IntersectionObserver(entries => { visible = entries[0].isIntersecting; schedule(); }, {threshold: .15}).observe(showcase);
  }
  if ('ResizeObserver' in window) new ResizeObserver(() => {
    if (compact.matches) {
      track.scrollTo({left: cards[current].offsetLeft - cards[0].offsetLeft, behavior: 'instant'});
      update();
    }
    schedule();
  }).observe(track);
  configure();
})();
