const purchaseForm = document.querySelector(".purchase-form");
const quantityInput = purchaseForm?.querySelector('input[name="cantidad"]');
const purchaseButton = purchaseForm?.querySelector("button");

if (quantityInput && purchaseButton) {
  function updatePurchaseLabel() {
    const quantity = Number(quantityInput.value);
    purchaseButton.textContent = quantity >= 2
      ? purchaseButton.dataset.pluralLabel
      : purchaseButton.dataset.singularLabel;
  }

  quantityInput.addEventListener("input", updatePurchaseLabel);
  updatePurchaseLabel();
}

if (purchaseForm) {
  document.querySelectorAll('input[name="funcion"]').forEach((input) => {
    input.addEventListener("change", () => {
      purchaseForm.action = input.dataset.purchaseUrl;
    });
  });
}
