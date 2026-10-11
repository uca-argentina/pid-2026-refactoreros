(() => {
  const card = document.querySelector('[data-ticket-status-url]');
  if (!card) return;

  const update = card.querySelector('[data-admission-update]');
  const title = card.querySelector('[data-admission-title]');
  const detail = card.querySelector('[data-admission-detail]');
  const remaining = card.querySelector('[data-admission-remaining]');
  let usedCount = Number(card.dataset.usedCount || 0);
  let polling = false;

  function plural(count, singular, pluralForm) {
    return count === 1 ? singular : pluralForm;
  }

  function showAdmission(payload) {
    const used = Number(payload.used_count || 0);
    const pending = Number(payload.remaining_count || 0);
    if (used === 0) {
      update.hidden = true;
      return;
    }
    title.textContent = `Ya tenés ${used} ${plural(used, 'butaca validada', 'butacas validadas')}`;
    detail.textContent = `${payload.room} · ${payload.used_seat_summary || 'Butacas registradas'}`;
    remaining.textContent = pending
      ? `Te ${pending === 1 ? 'queda' : 'quedan'} ${pending} ${plural(pending, 'butaca pendiente', 'butacas pendientes')} para entrar. ¡Que lo ${pending === 1 ? 'disfrutes' : 'disfruten'}!`
      : 'Ya ingresaron todas las personas. ¡Que lo disfruten!';
    update.hidden = false;
    update.classList.remove('is-arriving');
    window.requestAnimationFrame(() => update.classList.add('is-arriving'));
  }

  async function refreshStatus() {
    if (polling || document.hidden) return;
    polling = true;
    try {
      const response = await fetch(card.dataset.ticketStatusUrl, {
        headers: {Accept: 'application/json'},
        cache: 'no-store',
        credentials: 'same-origin',
      });
      if (!response.ok) return;
      const payload = await response.json();
      if (Number(payload.used_count || 0) !== usedCount) {
        usedCount = Number(payload.used_count || 0);
        showAdmission(payload);
      }
    } catch (_error) {
      // Silent retry: a status refresh must never interrupt the QR experience.
    } finally {
      polling = false;
    }
  }

  window.setInterval(refreshStatus, 5000);
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) refreshStatus();
  });
})();
