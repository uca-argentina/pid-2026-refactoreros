import {formatCurrency, parseSeatPrice} from "./shared/money.js";

(() => {
  const form = document.querySelector('[data-candy-store-form]');
  if (!form) return;
  const items = [...form.querySelectorAll('[data-candy-item]')];
  const button = form.querySelector('[data-candy-buy]');
  const lines = form.querySelector('[data-candy-cart-lines]');
  let submitting = false;
  function sync() {
    let total = 0;
    lines.replaceChildren();
    for (const item of items) {
      const quantity = Number(item.dataset.quantity || 0);
      if (!quantity) continue;
      const subtotal = quantity * (parseSeatPrice(item.dataset.price) ?? 0);
      total += subtotal;
      const line = document.createElement('li');
      line.textContent = `${quantity} × ${item.querySelector('h4').textContent} · ${formatCurrency(subtotal)}`;
      lines.append(line);
    }
    if (!lines.children.length) {
      const empty = document.createElement('li');
      empty.textContent = 'Elegí algo rico para empezar.';
      lines.append(empty);
    }
    form.querySelector('[data-candy-cart-total]').textContent = formatCurrency(total);
    const selected = items.some(item => Number(item.dataset.quantity || 0) > 0);
    button.disabled = submitting || !selected;
    button.textContent = submitting ? 'Procesando pedido…' : selected ? 'Comprar Candy' : 'Elegí productos para continuar';
  }
  document.addEventListener('candy:change', sync);
  form.addEventListener('submit', event => {
    if (submitting || button.disabled) { event.preventDefault(); return; }
    submitting = true;
    button.setAttribute('aria-busy', 'true');
    sync();
  });
  window.addEventListener('pageshow', () => { submitting = false; button.removeAttribute('aria-busy'); sync(); });
  sync();
})();
