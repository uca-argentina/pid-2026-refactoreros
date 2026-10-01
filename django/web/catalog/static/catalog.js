const purchaseForm = document.querySelector(".purchase-form");
const quantityInput = purchaseForm?.querySelector('input[name="cantidad"]');
const selectedSeatsInput = purchaseForm?.querySelector('input[name="selected_seats"]');
const quantityField = document.querySelector(".quantity-field");
const purchaseButton = purchaseForm?.querySelector('.purchase-action button[type="submit"]');
const purchaseError = document.querySelector(".purchase-error");
const seatMaps = document.querySelectorAll(".client-seat-map");

function serializeSelectedSeats(seatMap) {
  if (!selectedSeatsInput) {
    return;
  }

  const selectedSeats = seatMap
    ? Array.from(seatMap.querySelectorAll(".client-seat.is-selected")).map((seat) => ({
      label: seat.dataset.seatLabel,
      type_id: seat.dataset.seatTypeId,
      price: seat.dataset.seatPrice,
    }))
    : [];
  selectedSeatsInput.value = JSON.stringify(selectedSeats);
}

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

  seatMaps.forEach((seatMap) => {
    const isActive = seatMap.dataset.funcionId === input.value;
    seatMap.classList.toggle("is-hidden", !isActive);
    seatMap.querySelectorAll(".client-seat.is-selected").forEach((seat) => {
      seat.classList.remove("is-selected");
    });
  });
  serializeSelectedSeats(null);

  if (quantityInput) {
    quantityInput.value = available > 0 ? 1 : 0;
    quantityInput.max = available;
    quantityInput.dispatchEvent(new Event("input"));
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

document.querySelectorAll(".client-seat").forEach((seat) => {
  seat.addEventListener("click", () => {
    const selectedFunction = document.querySelector('input[name="funcion"]:checked');
    const available = Number(selectedFunction?.dataset.available || 0);
    const seatMap = seat.closest(".client-seat-map");
    const selectedSeats = seatMap.querySelectorAll(".client-seat.is-selected");

    if (!seat.classList.contains("is-selected") && selectedSeats.length >= available) {
      return;
    }

    seat.classList.toggle("is-selected");
    serializeSelectedSeats(seatMap);

    const nextQuantity = seatMap.querySelectorAll(".client-seat.is-selected").length || 1;
    if (quantityInput) {
      quantityInput.value = nextQuantity;
      quantityInput.dispatchEvent(new Event("input"));
    }
  });
});
