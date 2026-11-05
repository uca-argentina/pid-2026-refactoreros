(() => {
  'use strict';
  document.querySelectorAll('[data-spin-stepper]').forEach(stepper => {
    const input = stepper.querySelector('input');
    const minus = stepper.querySelector('[data-step="-1"]');
    const plus = stepper.querySelector('[data-step="1"]');
    const min = Number(input.min), max = Number(input.max);
    function sync() {
      minus.disabled = Number(input.value) <= min;
      plus.disabled = Number(input.value) >= max;
    }
    stepper.querySelectorAll('[data-step]').forEach(button => button.addEventListener('click', () => {
      const current = Number.isInteger(input.valueAsNumber) ? input.valueAsNumber : min;
      input.value = Math.min(max, Math.max(min, current + Number(button.dataset.step)));
      input.dispatchEvent(new Event('input', {bubbles:true}));
    }));
    input.addEventListener('input', sync);
    sync();
  });
})();
