const purchaseForm = document.querySelector(".purchase-form");
const quantityInput = purchaseForm?.querySelector('input[name="cantidad"]');
const quantityField = document.querySelector(".quantity-field");
const purchaseButton = purchaseForm?.querySelector("button");
const purchaseError = document.querySelector(".purchase-error");

if (quantityInput && purchaseButton) {
  function updatePurchaseLabel() {
    if (purchaseButton.disabled) {
      purchaseButton.textContent = purchaseButton.dataset.soldOutLabel;
      return;
    }

    const quantity = Number(quantityInput.value);
    purchaseButton.textContent = quantity >= 2
      ? purchaseButton.dataset.pluralLabel
      : purchaseButton.dataset.singularLabel;
  }

  quantityInput.addEventListener("input", updatePurchaseLabel);
  updatePurchaseLabel();
}

function updatePurchaseState(input) {
  const available = Number(input.dataset.available || 0);

  if (purchaseForm) {
    purchaseForm.action = input.dataset.purchaseUrl;
  }

  if (quantityField) {
    quantityField.hidden = available <= 0;
  }

  if (purchaseButton) {
    purchaseButton.disabled = available <= 0;
    if (available <= 0) {
      purchaseButton.textContent = purchaseButton.dataset.soldOutLabel;
    } else if (quantityInput) {
      const quantity = Number(quantityInput.value);
      purchaseButton.textContent = quantity >= 2
        ? purchaseButton.dataset.pluralLabel
        : purchaseButton.dataset.singularLabel;
    }
  }
}

document.querySelectorAll('input[name="funcion"]').forEach((input) => {
  if (input.checked) {
    updatePurchaseState(input);
  }

  input.addEventListener("change", () => {
    updatePurchaseState(input);
    if (purchaseError) {
      purchaseError.hidden = true;
    }
  });
});
