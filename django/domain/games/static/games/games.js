(() => {
  'use strict';
  const root = document.querySelector('[data-games]');
  if (!root) return;
  if (window.lucide) window.lucide.createIcons();
  let state = JSON.parse(document.getElementById('game-initial').textContent);
  let serverOffset = state.server_now ? Date.parse(state.server_now) - Date.now() : 0;
  let busy = false, rotation = 0, audioContext;
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  const $ = id => document.getElementById(id);
  const authenticated = root.dataset.authenticated === 'true';
  const dialog = $('games-dialog');
  let inventoryChanged = false;
  const outcomeDialog = $('game-outcome');
  let closing = false;
  function closeGames() {
    if (!dialog.open || closing) return;
    if (reduced.matches) { dialog.close(); return; }
    closing = true;
    dialog.style.setProperty('--game-close-opacity', getComputedStyle(dialog).opacity);
    dialog.classList.add('is-closing');
    let fallback;
    function finish(event) {
      if (event && (event.target !== dialog || event.animationName !== 'game-popup-fade-out')) return;
      clearTimeout(fallback);
      dialog.removeEventListener('animationend', finish);
      dialog.close();
      dialog.classList.remove('is-closing');
      dialog.style.removeProperty('--game-close-opacity');
      closing = false;
    }
    dialog.addEventListener('animationend', finish);
    fallback = setTimeout(() => finish(), 240);
  }
  const canTrivia = () => authenticated && (Boolean(state.run && !state.run.finished) || Boolean(state.can_start));
  let currentTab = 'wheel';
  function showTab(tab, focus = false) {
    currentTab = tab;
    ['wheel', 'trivia'].forEach(name => {
      $(`panel-${name}`).hidden = name !== tab;
      $(`tab-${name}`).setAttribute('aria-selected', String(name === tab));
      $(`tab-${name}`).tabIndex = name === tab ? 0 : -1;
    });
    if (focus) $(`tab-${tab}`).focus();
  }
  root.querySelectorAll('[data-game-tab]').forEach(button => {
    button.addEventListener('click', () => showTab(button.dataset.gameTab));
    button.addEventListener('keydown', event => {
      if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) {
        event.preventDefault(); showTab(currentTab === 'wheel' ? 'trivia' : 'wheel', true);
      }
    });
  });
  root.querySelectorAll('[data-show-trivia]').forEach(button => button.addEventListener('click', () => showTab('trivia', true)));
  root.querySelectorAll('[data-show-wheel]').forEach(button => button.addEventListener('click', () => showTab('wheel', true)));
  $('games-launcher').addEventListener('click', async () => {
    if (dialog.open) return;
    dialog.showModal(); document.body.classList.add('games-modal-open');
    if (authenticated && !busy) {
      try {
        const response = await fetch(`${root.dataset.api}api/state/`, {credentials: 'same-origin'});
        if (response.ok && !response.redirected) { const fresh = await response.json(); if (!busy) { state = fresh; serverOffset = Date.parse(state.server_now) - Date.now(); drawWheel(state.layout); render(); } }
      } catch (_) { /* Initial state remains playable; mutations revalidate it. */ }
    }
  });
  $('games-close').addEventListener('click', closeGames);
  dialog.addEventListener('cancel', event => { if (event.target === dialog) { event.preventDefault(); closeGames(); } });
  document.querySelectorAll('[data-open-games]').forEach(button => button.addEventListener('click', () => $('games-launcher').click()));
  dialog.addEventListener('click', event => { if (event.target === dialog) { const r = dialog.getBoundingClientRect(); if (event.clientX < r.left || event.clientX > r.right || event.clientY < r.top || event.clientY > r.bottom) closeGames(); } });
  dialog.addEventListener('close', () => {
    document.body.classList.remove('games-modal-open');
    if (inventoryChanged && document.querySelector('[data-prize-inventory]')) { location.reload(); return; }
    $('games-launcher').focus({preventScroll:true});
  });
  let sound = true;
  try { sound = localStorage.getItem('games-sound') !== 'off'; } catch (_) { /* Private browsing */ }
  const soundButton = $('sound-toggle');
  function renderSound() {
    const label = sound ? 'Silenciar sonido' : 'Activar sonido';
    soundButton.setAttribute('aria-label', label); soundButton.title = label;
    soundButton.setAttribute('aria-pressed', String(sound));
    soundButton.querySelector('[data-sound-on]').toggleAttribute('hidden', !sound);
    soundButton.querySelector('[data-sound-off]').toggleAttribute('hidden', sound);
  }
  function tone(win) {
    if (!sound) return;
    try {
      audioContext ||= new (window.AudioContext || window.webkitAudioContext)();
      audioContext.resume();
      [0, .13, .26].forEach((delay, i) => {
        const oscillator = audioContext.createOscillator(), gain = audioContext.createGain();
        oscillator.connect(gain); gain.connect(audioContext.destination);
        oscillator.frequency.value = win ? [523, 659, 784][i] : [330, 260, 196][i];
        const at = audioContext.currentTime + delay;
        gain.gain.setValueAtTime(.045, at); gain.gain.exponentialRampToValueAtTime(.001, at + .16);
        oscillator.start(at); oscillator.stop(at + .18);
      });
    } catch (_) { /* Sound is optional. */ }
  }
  soundButton.addEventListener('click', () => { sound = !sound; try { localStorage.setItem('games-sound', sound ? 'on' : 'off'); } catch (_) {} renderSound(); if (sound) tone(true); });
  renderSound();
  function celebrate() {
    if (reduced.matches) return;
    const area = $('game-confetti');
    for (let i = 0; i < 36; i++) {
      const particle = document.createElement('i');
      particle.style.left = `${Math.random() * 100}%`; particle.style.background = ['#f45947', '#ffd384', '#fff0cc'][i % 3];
      particle.style.animationDelay = `${Math.random() * .4}s`; area.append(particle);
    }
    setTimeout(() => area.replaceChildren(), 2700);
  }
  function node(tag, text, className) { const el = document.createElement(tag); el.textContent = text; if (className) el.className = className; return el; }
  function resultIcon(kind) {
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('fill', 'none'); svg.setAttribute('stroke', 'currentColor');
    svg.setAttribute('stroke-width', '2'); svg.setAttribute('stroke-linecap', 'round');
    svg.setAttribute('stroke-linejoin', 'round'); svg.setAttribute('aria-hidden', 'true');
    const paths = {
      over: 'M18 6 6 18M6 6l12 12',
      spin: 'M20 4v6h-6M20 10a8 8 0 1 0-1 8',
      prize: 'M8 3h8v6a4 4 0 0 1-8 0V3ZM8 5H4v2a4 4 0 0 0 4 4M16 5h4v2a4 4 0 0 1-4 4M12 13v5M8 21h8M10 18h4v3h-4z',
      attempt: 'M9 9a3 3 0 1 1 5 2c-1 1-2 1-2 3M12 18h.01'
    };
    const path = document.createElementNS(svg.namespaceURI, 'path');
    path.setAttribute('d', paths[kind] || paths.prize); svg.append(path);
    return svg;
  }
  function showOutcome(outcome) {
    const over = outcome.kind === 'over';
    outcomeDialog.classList.toggle('is-game-over', over);
    $('outcome-symbol').replaceChildren(resultIcon(outcome.kind));
    $('outcome-kicker').textContent = over ? 'FIN DE LA TIRADA' : '¡PREMIO GANADO!';
    $('outcome-title').textContent = over ? 'GAME OVER' : (outcome.coupon?.label || outcome.label);
    $('outcome-description').textContent = over ? `Esta vez no hubo premio. Te quedan ${state.spins} tiradas.` : outcome.kind === 'prize' ? 'Ya está en Mis premios. Elegí cuándo retirarlo en Candy.' : outcome.kind === 'spin' ? 'Sumaste una tirada. Esta casilla ya salió de tu ruleta; el resto se redistribuyó.' : 'Sumaste una oportunidad para la trivia.';
    $('outcome-inventory').hidden = outcome.kind !== 'prize';
    $('outcome-continue').textContent = state.spins ? 'Volver a girar ↻' : canTrivia() ? 'Ganar tiradas →' : 'Entendido';
    outcomeDialog.showModal();
  }
  $('outcome-continue').addEventListener('click', () => { outcomeDialog.close(); if (!state.spins && canTrivia()) showTab('trivia', true); });
  function drawWheel(layout) {
    const wheel = $('prize-wheel');
    wheel.replaceChildren();
    const colors = ['#bf2438', '#63202b', '#da4938', '#3c1720', '#a33129', '#866031'];
    if (!layout.length) { wheel.style.background = '#32141a'; return; }
    const part = 360 / layout.length;
    wheel.style.background = `conic-gradient(${layout.map((_, i) => `${colors[i % colors.length]} ${i * part}deg ${(i + 1) * part}deg`).join(',')})`;
    layout.forEach((slot, i) => {
      const dense = layout.length > 12;
      const label = node('span', '', `wheel-label${dense ? ' is-dense' : ''}`);
      label.append(node('span', slot.label, 'wheel-label-text'), resultIcon(slot.kind));
      label.style.transform = `rotate(${i * part + part / 2 - 90}deg) translateX(${dense ? 95 : 62}px) translateY(-50%)`; wheel.append(label);
    });
  }
  function render() {
    $('spin-balance').textContent = state.spins; $('attempt-balance').textContent = state.extra_attempts;
    $('launcher-balance').textContent = state.spins;
    const playable = canTrivia();
    root.querySelectorAll('[data-show-wheel]').forEach(button => { button.hidden = playable; });
    const disabled = busy || !authenticated || (state.spins ? !state.layout.length : !playable);
    $('wheel-hub').disabled = disabled;
    $('wheel-hub').querySelector('small').textContent = state.spins || !playable ? 'GIRAR' : 'GANAR';
    $('wheel-hub').setAttribute('aria-label', state.spins || !playable ? 'Girar ruleta' : 'Ganar tiradas');
    $('earn-spins').classList.toggle('is-highlighted', !state.spins);
    $('earn-spins').hidden = state.spins > 0 || !playable;
    const active = state.run && !state.run.finished;
    const extra = active ? state.run.source === 'extra' : !state.daily_ready && state.extra_attempts > 0;
    $('trivia-title').textContent = extra ? 'Trivia extra' : 'Trivia diaria';
    $('trivia-rules').textContent = extra ? 'Una pregunta. Si acertás, ganás una tirada. Un error o agotar el tiempo termina la partida.' : 'Hasta 3 preguntas. Cada acierto, una tirada. Un error o agotar el tiempo termina la partida.';
    $('start-trivia').replaceChildren(node('span', extra ? 'Empezar trivia extra' : 'Empezar trivia'), node('span', '↗'));
    $('earn-spins').replaceChildren(node('span', extra ? 'Jugá tu trivia extra y ganá una tirada' : 'Jugá la trivia y ganá hasta 3 tiradas'), node('span', '→'));
    $('start-trivia').hidden = Boolean(active) || (authenticated && !state.can_start); $('start-trivia').disabled = busy || !authenticated || !state.can_start;
    const progress = $('trivia-progress'); progress.replaceChildren();
    for (let i = 0; i < (active ? state.run.total : extra ? 1 : 3); i++) progress.append(node('span', '', active && i < state.run.step ? 'is-done' : active && i === state.run.step ? 'is-current' : ''));
    const area = $('question-area'); area.replaceChildren();
    if (active) {
      const run = state.run, question = run.question;
      area.append(node('p', `${['', 'FÁCIL', 'MEDIA', 'DIFÍCIL'][question.difficulty]} · PREGUNTA ${run.step + 1} DE ${run.total}`, 'game-difficulty'));
      const heading = node('h3', question.text, 'game-question'); heading.tabIndex = -1; area.append(heading);
      const options = node('div', '', 'game-options');
      question.options.forEach((option, choice) => {
        const button = node('button', '', 'game-option'); button.type = 'button'; button.disabled = busy;
        button.append(node('b', ['A', 'B', 'C'][choice]), node('span', option));
        button.addEventListener('click', () => perform('answer', {run: run.id, step: run.step, choice})); options.append(button);
      }); area.append(options);
    } else if (authenticated && !state.daily_ready && !state.extra_attempts) {
      area.append(node('h3', '¡No te quedan más preguntas por hoy!', 'trivia-exhausted'), node('p', '¡Te esperamos mañana!', 'trivia-tomorrow'));
    } else if (authenticated && !state.bank_ready) {
      area.append(node('h3', 'Por ahora no hay preguntas disponibles', 'trivia-exhausted'), node('p', 'Conservás tu oportunidad. Volvé más tarde.', 'trivia-tomorrow'));
    } else area.append(node('p', 'Una respuesta correcta = una tirada. ¿Listo para jugar?', 'game-question'));
    $('trivia-progress').hidden = !active && authenticated && !state.can_start;
    updateTimer();
    cooldown();
  }
  let timeoutPending = null;
  function updateTimer() {
    const timer = $('question-timer'), run = state.run;
    const active = Boolean(run && !run.finished);
    timer.hidden = !active;
    if (!active) return;
    const seconds = Math.max(0, Math.ceil((Date.parse(run.deadline) - Date.now() - serverOffset) / 1000));
    timer.textContent = `${seconds} s`; timer.classList.toggle('is-urgent', seconds <= 3);
    const identity = `${run.id}:${run.step}`;
    if (!seconds && !busy && timeoutPending !== identity) {
      timeoutPending = identity;
      perform('answer', {run: run.id, step: run.step, choice: null}).finally(() => { setTimeout(() => { timeoutPending = null; }, 2000); });
    }
  }
  function cooldown() {
    const hasTrivia = state.daily_ready || state.extra_attempts > 0 || Boolean(state.run && !state.run.finished);
    const showCountdown = Boolean(authenticated && !hasTrivia && state.next_daily_at);
    $('cooldown').hidden = !showCountdown;
    $('cooldown').classList.toggle('is-countdown', showCountdown);
    if (!showCountdown) { $('cooldown').replaceChildren(); return; }
    const seconds = Math.max(0, Math.ceil((new Date(state.next_daily_at) - Date.now()) / 1000));
    if (!seconds && !busy && authenticated) {
      fetch(`${root.dataset.api}api/state/`, {credentials:'same-origin'}).then(r => r.ok && !r.redirected ? r.json() : null).then(fresh => { if (fresh && !busy) { state=fresh; render(); } }).catch(() => {});
      return;
    }
    const h = Math.floor(seconds / 3600), m = Math.floor(seconds % 3600 / 60), s = seconds % 60;
    $('cooldown').replaceChildren(
      node('span', 'Próxima trivia en', 'cooldown-label'),
      node('strong', `${h} h ${String(m).padStart(2, '0')} m ${String(s).padStart(2, '0')} s`, 'cooldown-time')
    );
  }
  // Persist unresolved operation keys across refreshes: a timeout must not spend twice.
  function pending(action, payload) {
    const storageKey = `games-pending-${action}`, signature = JSON.stringify(payload);
    try {
      const saved = JSON.parse(sessionStorage.getItem(storageKey) || 'null');
      if (saved?.signature === signature) return saved.key;
    } catch (_) {}
    const key = crypto.randomUUID();
    try { sessionStorage.setItem(storageKey, JSON.stringify({signature, key})); } catch (_) {}
    return key;
  }
  async function perform(action, payload = {}) {
    if (busy) return;
    busy = true; $('game-error').hidden = true; $('game-status').textContent = 'Preparando tu jugada…'; render();
    try {
      const key = pending(action, payload);
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 20000);
      let response;
      try {
        response = await fetch(`${root.dataset.api}api/${action}/`, {method: 'POST', credentials: 'same-origin', signal: controller.signal,
          headers: {'Content-Type': 'application/json', 'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value}, body: JSON.stringify({...payload, key})});
      } finally { clearTimeout(timeout); }
      if (response.redirected) throw new Error('Tu sesión venció. Volvé a iniciar sesión.');
      const result = await response.json();
      if (!response.ok) {
        if (!result.retry) { try { sessionStorage.removeItem(`games-pending-${action}`); } catch (_) {} }
        throw new Error(result.error || 'No pudimos completar la jugada.');
      }
      state = result.state;
      serverOffset = Date.parse(state.server_now) - Date.now();
      if (action === 'spin') {
        const outcome = result.spin; drawWheel(outcome.layout);
        if (outcome.kind === 'prize') inventoryChanged = true;
        $('game-status').textContent = 'La suerte está girando…'; $('wheel-result').textContent = '';
        const target = 360 - (outcome.index + .5) * 360 / outcome.layout.length;
        rotation = Math.ceil(rotation / 360) * 360 + 5 * 360 + target;
        // Commit the returned layout before rotating to its server-selected segment.
        $('prize-wheel').getBoundingClientRect();
        $('prize-wheel').style.transform = `rotate(${rotation}deg)`;
        if (!reduced.matches) await new Promise(resolve => setTimeout(resolve, 4100));
        $('wheel-result').textContent = outcome.label;
        tone(outcome.kind !== 'over'); if (outcome.kind !== 'over') celebrate();
        $('game-status').textContent = outcome.kind === 'prize' ? '¡Premio ganado! Se sumó a Mis premios. Elegí cuándo retirarlo.' : outcome.kind === 'over' ? 'Esta vez no hubo premio. ¡La próxima puede ser tuya!' : `¡Ganaste: ${outcome.label}!`;
        // Reset rotation without animation when redistributing the server's next layout.
        $('prize-wheel').style.transition = 'none'; rotation = 0; $('prize-wheel').style.transform = 'rotate(0deg)';
        drawWheel(state.layout); $('prize-wheel').getBoundingClientRect(); $('prize-wheel').style.transition = '';
        if (dialog.open && !closing) showOutcome(outcome);
      } else if (action === 'answer') {
        tone(result.correct);
        $('game-status').textContent = result.timed_out ? 'Se terminó el tiempo. Conservás las tiradas que ganaste.' : result.correct ? (result.run.finished ? '¡Trivia completada! Tus tiradas te esperan.' : '¡Correcto! +1 tirada. Vamos por la siguiente.') : 'Esta vez no fue. Conservás todas las tiradas que ganaste.';
        if (result.correct) celebrate();
      } else $('game-status').textContent = '¡Acción! Elegí tu respuesta.';
      try { sessionStorage.removeItem(`games-pending-${action}`); } catch (_) {}
    } catch (error) {
      $('game-error').textContent = error.name === 'AbortError' ? 'La conexión tardó demasiado. Reintentá para recuperar el resultado.' : error.message;
      $('game-error').hidden = false; $('game-status').textContent = 'Podés reintentar la jugada.';
    } finally { busy = false; render(); if (action !== 'spin') document.querySelector('.game-question')?.focus({preventScroll: true}); }
  }
  $('start-trivia').addEventListener('click', () => perform('start'));
  function playWheel() { if (!busy) { if (state.spins) perform('spin'); else if (canTrivia()) showTab('trivia', true); } }
  $('wheel-hub').addEventListener('click', playWheel);
  drawWheel(state.layout); render(); setInterval(cooldown, 1000); setInterval(updateTimer, 200);
  showTab('wheel');
  if (new URLSearchParams(location.search).get('juegos') === '1') $('games-launcher').click();
})();
