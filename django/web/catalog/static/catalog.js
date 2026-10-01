const purchaseForm = document.querySelector(".purchase-form");
const selectedSeatsInput = purchaseForm?.querySelector('input[name="selected_seats"]');
const purchaseButton = purchaseForm?.querySelector('.purchase-action button[type="submit"]');
const purchaseError = document.querySelector(".purchase-error");
const purchaseSummary = document.querySelector("[data-purchase-summary]");
const reservationSummary = document.querySelector("[data-reservation-summary]");
const reservationSummaryText = document.querySelector("[data-reservation-summary-text]");
const cartSeatLines = document.querySelector("[data-cart-seat-lines]");
const cartTotal = document.querySelector("[data-cart-total]");
const seatMaps = document.querySelectorAll(".client-seat-map");
let reservationExpiresAt = null;
let reservationTimer = null;

function getActiveSeatMap() {
  return Array.from(seatMaps).find((seatMap) => !seatMap.classList.contains("is-hidden"));
}

function serializeSelectedSeats(seatMap) {
  if (!selectedSeatsInput) {
    return;
  }

  const selectedSeats = seatMap
    ? Array.from(seatMap.querySelectorAll("button.client-seat.is-selected")).map((seat) => ({
      label: seat.dataset.seatLabel,
      type_id: seat.dataset.seatTypeId,
      price: seat.dataset.seatPrice,
    }))
    : [];
  selectedSeatsInput.value = JSON.stringify(selectedSeats);
}

function selectedSeatsFor(seatMap) {
  return seatMap ? Array.from(seatMap.querySelectorAll("button.client-seat.is-selected")) : [];
}

function formatMoney(value) {
  return value.toLocaleString("es-AR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function csrfToken() {
  return purchaseForm?.querySelector('input[name="csrfmiddlewaretoken"]')?.value || "";
}

function refreshIntervalMs(seatMap) {
  const seconds = Number(seatMap?.dataset.refreshIntervalSeconds || 5);
  return Math.max(seconds, 1) * 1000;
}

function formatTimeLeft(milliseconds) {
  const seconds = Math.max(Math.ceil(milliseconds / 1000), 0);
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  return `${minutes}:${String(remainingSeconds).padStart(2, "0")}`;
}

function updateReservationSummary() {
  if (!reservationSummary) {
    return;
  }
  if (!reservationExpiresAt) {
    reservationSummary.hidden = true;
    if (reservationSummaryText) {
      reservationSummaryText.textContent = "";
    }
    return;
  }
  const milliseconds = reservationExpiresAt.getTime() - Date.now();
  if (milliseconds <= 0) {
    reservationSummary.hidden = false;
    if (reservationSummaryText) {
      reservationSummaryText.textContent = "Reserva vencida. Volvé a seleccionar tus butacas.";
    }
    return;
  }
  reservationSummary.hidden = false;
  if (reservationSummaryText) {
    reservationSummaryText.textContent = `Reservando tus butacas: ${formatTimeLeft(milliseconds)}`;
  }
}

function setReservationExpiration(reservations) {
  const expirations = (reservations || [])
    .map((reservation) => new Date(reservation.expires_at))
    .filter((date) => !Number.isNaN(date.getTime()));
  reservationExpiresAt = expirations.length
    ? new Date(Math.min(...expirations.map((date) => date.getTime())))
    : null;
  if (!reservationTimer) {
    reservationTimer = window.setInterval(updateReservationSummary, 1000);
  }
  updateReservationSummary();
}

function markSeatUnavailable(seat) {
  seat.classList.remove("is-selected", "is-pending");
  seat.classList.add("is-unavailable");
  seat.disabled = true;
  seat.setAttribute("aria-disabled", "true");
}

function markSeatAvailable(seat) {
  seat.classList.remove("is-unavailable");
  seat.disabled = false;
  seat.removeAttribute("aria-disabled");
}

function markUnavailableSeats(seatMap, labels) {
  const unavailable = new Set(labels || []);
  seatMap?.querySelectorAll("button.client-seat").forEach((seat) => {
    if (unavailable.has(seat.dataset.seatLabel)) {
      markSeatUnavailable(seat);
    } else {
      markSeatAvailable(seat);
    }
  });
}

async function syncSeatStatus(seatMap) {
  const statusUrl = seatMap?.dataset.reservationStatusUrl;
  if (!statusUrl) {
    return;
  }
  const response = await fetch(statusUrl, {headers: {"Accept": "application/json"}});
  if (!response.ok) {
    return;
  }
  const payload = await response.json();
  markUnavailableSeats(seatMap, payload.unavailable);
  const ownReserved = new Set((payload.reserved || []).map((reservation) => reservation.label));
  seatMap?.querySelectorAll("button.client-seat").forEach((seat) => {
    if (ownReserved.has(seat.dataset.seatLabel) && !seat.classList.contains("is-unavailable")) {
      seat.classList.add("is-selected");
    } else if (seat.classList.contains("is-selected")) {
      seat.classList.remove("is-selected");
    }
  });
  setReservationExpiration(payload.reserved);
  serializeSelectedSeats(seatMap);
  updateSeatDrivenPurchaseState();
}

async function requestSeatReservation(seat, action) {
  const seatMap = seat.closest(".client-seat-map");
  const reservationUrl = seatMap?.dataset.reservationUrl;
  if (!reservationUrl) {
    return {ok: true};
  }
  const response = await fetch(reservationUrl, {
    method: "POST",
    headers: {
      "Accept": "application/json",
      "Content-Type": "application/json",
      "X-CSRFToken": csrfToken(),
    },
    body: JSON.stringify({action, label: seat.dataset.seatLabel}),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || !payload.ok) {
    markUnavailableSeats(seatMap, payload.unavailable || [seat.dataset.seatLabel]);
    throw new Error(payload.error || "La butaca ya no está disponible.");
  }
  await syncSeatStatus(seatMap);
  return payload;
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

  if (purchaseSummary) {
    purchaseSummary.hidden = !requiresSeatSelection || selectedCount > 0;
    if (!requiresSeatSelection) {
      purchaseSummary.textContent = "";
    } else if (selectedCount === 0) {
      purchaseSummary.textContent = "Seleccioná al menos una butaca para continuar";
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
    seatMap.querySelectorAll("button.client-seat.is-selected").forEach((seat) => {
      seat.classList.remove("is-selected");
    });
  });
  serializeSelectedSeats(null);

  if (purchaseButton) {
    purchaseButton.disabled = available <= 0 || Boolean(activeSeatMap);
    if (available <= 0) {
      purchaseButton.textContent = purchaseButton.dataset.soldOutLabel;
    } else if (activeSeatMap) {
      purchaseButton.textContent = purchaseButton.dataset.selectSeatLabel;
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

document.querySelectorAll("button.client-seat").forEach((seat) => {
  seat.addEventListener("click", async () => {
    if (seat.disabled || seat.classList.contains("is-unavailable") || seat.classList.contains("is-pending")) {
      return;
    }
    const seatMap = seat.closest(".client-seat-map");
    const selectedFunction = document.querySelector('input[name="funcion"]:checked');
    const available = Number(selectedFunction?.dataset.available || seatMap?.dataset.available || 0);
    const selectedSeats = selectedSeatsFor(seatMap);

    if (!seat.classList.contains("is-selected") && selectedSeats.length >= available) {
      return;
    }

    seat.classList.add("is-pending");
    try {
      if (seat.classList.contains("is-selected")) {
        await requestSeatReservation(seat, "release");
        seat.classList.remove("is-selected");
      } else {
        await requestSeatReservation(seat, "reserve");
        seat.classList.add("is-selected");
      }
      serializeSelectedSeats(seatMap);
      updateSeatDrivenPurchaseState();
    } catch (error) {
      if (purchaseSummary) {
        purchaseSummary.hidden = false;
        purchaseSummary.textContent = error.message;
      }
    } finally {
      seat.classList.remove("is-pending");
    }
  });
});

seatMaps.forEach((seatMap) => {
  syncSeatStatus(seatMap);
  window.setInterval(() => syncSeatStatus(seatMap), refreshIntervalMs(seatMap));
});

purchaseForm?.addEventListener("submit", (event) => {
  const activeSeatMap = getActiveSeatMap();
  if (activeSeatMap && selectedSeatsFor(activeSeatMap).length === 0) {
    event.preventDefault();
    updateSeatDrivenPurchaseState();
  }
});
