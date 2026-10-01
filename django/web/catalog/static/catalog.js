const purchaseForm = document.querySelector(".purchase-form");
const quantityInput = purchaseForm?.querySelector('input[name="cantidad"]');
const selectedSeatsInput = purchaseForm?.querySelector('input[name="selected_seats"]');
const quantityField = document.querySelector(".quantity-field");
const purchaseButton = purchaseForm?.querySelector('.purchase-action button[type="submit"]');
const purchaseError = document.querySelector(".purchase-error");
const purchaseSummary = document.querySelector("[data-purchase-summary]");
const cartSeatLines = document.querySelector("[data-cart-seat-lines]");
const cartTotal = document.querySelector("[data-cart-total]");
const seatMaps = document.querySelectorAll(".client-seat-map");

function getActiveSeatMap() {
  return Array.from(seatMaps).find((seatMap) => !seatMap.classList.contains("is-hidden"));
}

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

function selectedSeatsFor(seatMap) {
  return seatMap ? Array.from(seatMap.querySelectorAll(".client-seat.is-selected")) : [];
}

function formatMoney(value) {
  return value.toLocaleString("es-AR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function updateSeatDrivenPurchaseState() {
  const activeSeatMap = getActiveSeatMap();
  const selectedSeats = selectedSeatsFor(activeSeatMap);
  const requiresSeatSelection = Boolean(activeSeatMap);
  const selectedCount = selectedSeats.length;
  const total = selectedSeats.reduce(
    (sum, seat) => sum + Number(seat.dataset.seatPrice || 0),
    0,
  );

  if (quantityField && requiresSeatSelection) {
    quantityField.hidden = true;
  }

  if (quantityInput && requiresSeatSelection) {
    quantityInput.value = selectedCount || 1;
    quantityInput.dispatchEvent(new Event("input"));
  }

  if (purchaseSummary) {
    purchaseSummary.hidden = !requiresSeatSelection;
    if (!requiresSeatSelection) {
      purchaseSummary.textContent = "";
    } else if (selectedCount === 0) {
      purchaseSummary.textContent = "Seleccioná una butaca para continuar.";
    } else {
      const labels = selectedSeats.map((seat) => seat.dataset.seatLabel).join(", ");
      const ticketLabel = selectedCount === 1 ? "butaca" : "butacas";
      purchaseSummary.textContent = `${selectedCount} ${ticketLabel}: ${labels} · Total $${formatMoney(total)}`;
    }
  }

  if (cartSeatLines) {
    cartSeatLines.innerHTML = "";
    if (selectedCount === 0) {
      const emptyItem = document.createElement("li");
      emptyItem.textContent = "Sin seleccionar";
      cartSeatLines.appendChild(emptyItem);
    } else {
      selectedSeats.forEach((seat) => {
        const item = document.createElement("li");
        const label = document.createElement("span");
        const price = document.createElement("strong");

        label.textContent = seat.dataset.seatLabel;
        price.textContent = `$${formatMoney(Number(seat.dataset.seatPrice || 0))}`;
        item.appendChild(label);
        item.appendChild(price);
        cartSeatLines.appendChild(item);
      });
    }
  }

  if (cartTotal) {
    cartTotal.textContent = `$${formatMoney(total)}`;
  }

  if (purchaseButton && requiresSeatSelection) {
    purchaseButton.disabled = selectedCount === 0;
    if (selectedCount === 0) {
      purchaseButton.textContent = purchaseButton.dataset.selectSeatLabel;
    } else {
      purchaseButton.textContent = selectedCount >= 2
        ? purchaseButton.dataset.pluralLabel
        : purchaseButton.dataset.singularLabel;
    }
  }
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
  let activeSeatMap = null;

  if (purchaseForm) {
    purchaseForm.action = input.dataset.purchaseUrl;
  }

  seatMaps.forEach((seatMap) => {
    const isActive = seatMap.dataset.funcionId === input.value;
    seatMap.classList.toggle("is-hidden", !isActive);
    if (isActive) {
      activeSeatMap = seatMap;
    }
    seatMap.querySelectorAll(".client-seat.is-selected").forEach((seat) => {
      seat.classList.remove("is-selected");
    });
  });
  serializeSelectedSeats(null);

  if (quantityField) {
    quantityField.hidden = available <= 0 || Boolean(activeSeatMap);
  }

  if (quantityInput) {
    quantityInput.value = available > 0 ? 1 : 0;
    quantityInput.max = available;
    quantityInput.dispatchEvent(new Event("input"));
  }

  if (purchaseButton) {
    purchaseButton.disabled = available <= 0 || Boolean(activeSeatMap);
    if (available <= 0) {
      purchaseButton.textContent = purchaseButton.dataset.soldOutLabel;
    } else if (activeSeatMap) {
      purchaseButton.textContent = purchaseButton.dataset.selectSeatLabel;
    } else if (quantityInput) {
      const quantity = Number(quantityInput.value);
      purchaseButton.textContent = quantity >= 2
        ? purchaseButton.dataset.pluralLabel
        : purchaseButton.dataset.singularLabel;
    }
  }
  updateSeatDrivenPurchaseState();
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

if (!document.querySelector('input[name="funcion"]')) {
  updateSeatDrivenPurchaseState();
}

document.querySelectorAll(".client-seat").forEach((seat) => {
  seat.addEventListener("click", () => {
    if (seat.disabled || seat.classList.contains("is-unavailable")) {
      return;
    }
    const seatMap = seat.closest(".client-seat-map");
    const selectedFunction = document.querySelector('input[name="funcion"]:checked');
    const available = Number(selectedFunction?.dataset.available || seatMap?.dataset.available || 0);
    const selectedSeats = selectedSeatsFor(seatMap);

    if (!seat.classList.contains("is-selected") && selectedSeats.length >= available) {
      return;
    }

    seat.classList.toggle("is-selected");
    serializeSelectedSeats(seatMap);
    updateSeatDrivenPurchaseState();
  });
});

purchaseForm?.addEventListener("submit", (event) => {
  const activeSeatMap = getActiveSeatMap();
  if (activeSeatMap && selectedSeatsFor(activeSeatMap).length === 0) {
    event.preventDefault();
    updateSeatDrivenPurchaseState();
  }
});
