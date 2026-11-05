(() => {
  const picker = document.querySelector("[data-candy-picker]");
  if (!picker) return;

  const input = picker.querySelector('input[name="candy_items"]');
  const items = [...picker.querySelectorAll("[data-candy-item]")];

  function quantityOf(item) {
    return Number(item.dataset.quantity || 0);
  }

  function syncSelection() {
    const selection = items
      .filter((item) => quantityOf(item) > 0)
      .map((item) => ({
        kind: item.dataset.kind,
        id: Number(item.dataset.id),
        quantity: quantityOf(item),
      }));
    input.value = selection.length ? JSON.stringify(selection) : "";
    document.dispatchEvent(new CustomEvent("candy:change"));
  }

  items.forEach((item) => {
    const output = item.querySelector("[data-candy-quantity]");
    const decrease = item.querySelector('[data-candy-step="-1"]');
    const increase = item.querySelector('[data-candy-step="1"]');
    if (!output || !decrease || !increase) return;
    const max = Number(item.dataset.max || 0);

    function setQuantity(quantity) {
      const next = Math.min(Math.max(quantity, 0), max);
      item.dataset.quantity = String(next);
      output.textContent = String(next);
      decrease.disabled = next === 0;
      increase.disabled = next >= max;
      item.classList.toggle("is-selected", next > 0);
      syncSelection();
    }

    decrease.addEventListener("click", () => setQuantity(quantityOf(item) - 1));
    increase.addEventListener("click", () => setQuantity(quantityOf(item) + 1));
  });
})();
