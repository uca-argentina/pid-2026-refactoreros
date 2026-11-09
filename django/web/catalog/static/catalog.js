import {formatMoney, parseSeatPrice} from "./shared/money.js";
import {initializeSeatMapViewport} from "./checkout/viewport.js";
import {createReservationApi} from "./checkout/api.js";

const purchaseForm = document.querySelector(".purchase-form");
const selectedSeatsInput = purchaseForm?.querySelector('input[name="selected_seats"]');
const purchaseButton = purchaseForm?.querySelector('.purchase-action button[type="submit"]');
const purchaseError = document.querySelector(".purchase-error");
const purchaseSummary = document.querySelector("[data-purchase-summary]");
const reservationSummary = document.querySelector("[data-reservation-summary]");
const reservationSummaryText = document.querySelector("[data-reservation-summary-text]");
const cartSeatLines = document.querySelector("[data-cart-seat-lines]");
const cartTotal = document.querySelector("[data-cart-total]");
const cartBaseTotal = document.querySelector("[data-cart-base-total]");
const purchaseSavings = document.querySelector("[data-purchase-savings]");
const purchaseSavingsAmount = document.querySelector("[data-purchase-savings-amount]");
const purchasePromotions = document.querySelector("[data-purchase-promotions]");
const purchasePromotionsList = document.querySelector("[data-purchase-promotions-list]");
const cartCandyRow = document.querySelector("[data-cart-candy-row]");
const cartCandyLines = document.querySelector("[data-cart-candy-lines]");
const seatMaps = document.querySelectorAll(".client-seat-map");
let reservationExpiresAt = null;
let reservationTimer = null;
let submitAfterReservationFlush = false;
let purchaseSubmitting = false;
let purchasePreparing = false;
const pendingSeatOperations = new WeakMap();
const pendingSeatTimers = new WeakMap();
const pendingSeatFlushes = new WeakMap();

const {sendSeatOperations} = createReservationApi({
  csrfToken, markUnavailableSeats, applyReservationState, syncSeatStatus,
});

function setPurchaseProcessing(processing) {
  if (!purchaseButton) {
    return;
  }
  purchaseButton.disabled = processing;
  purchaseButton.classList.toggle("is-processing", processing);
  purchaseButton.setAttribute("aria-busy", String(processing));
  if (processing) {
    purchaseButton.innerHTML = '<span class="purchase-loading-clock" aria-hidden="true"></span>Procesando compra…';
  }
}

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

function seatPrice(seat) {
  return parseSeatPrice(seat?.dataset.seatPrice) ?? 0;
}

function seatBasePrice(seat) {
  return parseSeatPrice(seat?.dataset.seatBasePrice) ?? seatPrice(seat);
}

function selectedCandyItems() {
  return [...document.querySelectorAll("[data-candy-item]")].filter(
    (item) => Number(item.dataset.quantity || 0) > 0,
  );
}

function candyItemTotal(item) {
  return (parseSeatPrice(item.dataset.price) ?? 0) * Number(item.dataset.quantity || 0);
}

function renderCandyCart(candyItems) {
  if (!cartCandyRow || !cartCandyLines) {
    return;
  }
  cartCandyRow.hidden = candyItems.length === 0;
  cartCandyLines.innerHTML = "";
  candyItems.forEach((item) => {
    const line = document.createElement("li");
    const label = document.createElement("span");
    const price = document.createElement("strong");
    label.textContent = `${item.dataset.quantity} × ${item.dataset.name}`;
    price.textContent = `$${formatMoney(candyItemTotal(item))}`;
    line.appendChild(label);
    line.appendChild(price);
    cartCandyLines.appendChild(line);
  });
}

function csrfToken() {
  return purchaseForm?.querySelector('input[name="csrfmiddlewaretoken"]')?.value || "";
}

function refreshIntervalMs(seatMap) {
  const seconds = Number(seatMap?.dataset.refreshIntervalSeconds || 5);
  return Math.max(seconds, 1) * 1000;
}

function reservationBatchDelayMs(seatMap) {
  const milliseconds = Number(seatMap?.dataset.reservationBatchDelayMs || 1000);
  return Math.max(milliseconds, 0);
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

function applyReservationState(seatMap, payload) {
  markUnavailableSeats(seatMap, payload.unavailable);
  const ownReserved = new Set((payload.reserved || []).map((reservation) => reservation.label));
  seatMap?.querySelectorAll("button.client-seat").forEach((seat) => {
    if (seat.classList.contains("is-pending")) {
      return;
    }
    if (ownReserved.has(seat.dataset.seatLabel) && !seat.classList.contains("is-unavailable")) {
      seat.classList.add("is-selected");
    } else if (seat.classList.contains("is-selected") && !seat.classList.contains("is-pending")) {
      seat.classList.remove("is-selected");
    }
  });
  setReservationExpiration(payload.reserved);
  serializeSelectedSeats(seatMap);
  updateSeatDrivenPurchaseState();
}

async function syncSeatStatus(seatMap) {
  const statusUrl = seatMap?.dataset.reservationStatusUrl;
  if (!statusUrl) {
    return;
  }
  try {
    const response = await fetch(statusUrl, {headers: {"Accept": "application/json"}});
    if (!response.ok) {
      return;
    }
    const payload = await response.json();
    applyReservationState(seatMap, payload);
  } catch (_error) {
    return;
  }
}

function queuedOperationsFor(seatMap) {
  let queue = pendingSeatOperations.get(seatMap);
  if (!queue) {
    queue = new Map();
    pendingSeatOperations.set(seatMap, queue);
  }
  return queue;
}

function clearPendingState(seatMap, operations) {
  const queuedOperations = queuedOperationsFor(seatMap);
  operations.forEach((operation) => {
    const seat = seatMap.querySelector(`[data-seat-label="${operation.label}"]`);
    if (!queuedOperations.has(operation.label)) {
      seat?.classList.remove("is-pending");
    }
  });
}

async function flushSeatReservations(seatMap) {
  if (!seatMap) {
    return {ok: true};
  }

  const activeFlush = pendingSeatFlushes.get(seatMap);
  if (activeFlush) {
    return activeFlush.catch(() => null).then(() => {
      if (queuedOperationsFor(seatMap).size) {
        return flushSeatReservations(seatMap);
      }
      return {ok: true};
    });
  }

  window.clearTimeout(pendingSeatTimers.get(seatMap));
  pendingSeatTimers.delete(seatMap);

  const queue = queuedOperationsFor(seatMap);
  if (!queue.size) {
    return {ok: true};
  }

  const operations = Array.from(queue.values()).map(({action, label}) => ({action, label}));
  queue.clear();
  const flush = sendSeatOperations(seatMap, operations)
    .finally(() => {
      clearPendingState(seatMap, operations);
      pendingSeatFlushes.delete(seatMap);
      updateSeatDrivenPurchaseState();
    });
  pendingSeatFlushes.set(seatMap, flush);
  return flush;
}

function showReservationError(error) {
  if (purchaseSummary) {
    purchaseSummary.hidden = false;
    purchaseSummary.textContent = error.message;
  }
}

function queueSeatReservation(seat, action, flushImmediately = false) {
  const seatMap = seat.closest(".client-seat-map");
  const queue = queuedOperationsFor(seatMap);
  queue.set(seat.dataset.seatLabel, {
    action,
    label: seat.dataset.seatLabel,
  });
  seat.classList.add("is-pending");
  window.clearTimeout(pendingSeatTimers.get(seatMap));
  if (flushImmediately) {
    flushSeatReservations(seatMap).catch(showReservationError);
    return;
  }
  pendingSeatTimers.set(
    seatMap,
    window.setTimeout(() => {
      flushSeatReservations(seatMap).catch(showReservationError);
    }, reservationBatchDelayMs(seatMap)),
  );
}

function hasPendingSeatOperations(seatMap) {
  return Boolean(seatMap && (
    queuedOperationsFor(seatMap).size || pendingSeatFlushes.get(seatMap)
  ));
}

function updateSeatDrivenPurchaseState() {
  const activeSeatMap = getActiveSeatMap();
  const selectedSeats = selectedSeatsFor(activeSeatMap);
  const requiresSeatSelection = Boolean(activeSeatMap);
  const selectedCount = selectedSeats.length;
  const requiredCount = Number(activeSeatMap?.dataset.requiredQuantity || 0);
  const quantityValid = requiredCount ? selectedCount === requiredCount : selectedCount > 0;
  const seatStateUpdating = hasPendingSeatOperations(activeSeatMap);
  const candyItems = selectedCandyItems();
  const candyTotal = candyItems.reduce((sum, item) => sum + candyItemTotal(item), 0);
  const total = selectedSeats.reduce(
    (sum, seat) => sum + seatPrice(seat),
    candyTotal,
  );
  const baseTotal = selectedSeats.reduce(
    (sum, seat) => sum + seatBasePrice(seat),
    candyTotal,
  );
  renderCandyCart(candyItems);
  const savings = Math.max(baseTotal - total, 0);

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
        const price = document.createElement("span");

        label.textContent = seat.dataset.seatLabel;
        price.className = "cart-seat-price";
        if (seatBasePrice(seat) > seatPrice(seat)) {
          const previousPrice = document.createElement("del");
          previousPrice.textContent = `$${formatMoney(seatBasePrice(seat))}`;
          price.appendChild(previousPrice);
        }
        const currentPrice = document.createElement("strong");
        currentPrice.textContent = `$${formatMoney(seatPrice(seat))}`;
        price.appendChild(currentPrice);
        item.appendChild(label);
        item.appendChild(price);
        cartSeatLines.appendChild(item);
      });
    }
  }

  if (cartTotal) {
    cartTotal.textContent = `$${formatMoney(total)}`;
  }

  if (cartBaseTotal) {
    cartBaseTotal.hidden = savings <= 0;
    cartBaseTotal.textContent = `$${formatMoney(baseTotal)}`;
  }

  if (purchaseSavings && purchaseSavingsAmount) {
    purchaseSavings.hidden = savings <= 0;
    purchaseSavingsAmount.textContent = `$${formatMoney(savings)}`;
  }

  if (purchasePromotions && purchasePromotionsList) {
    const promotions = [...new Set(
      selectedSeats.map((seat) => (seat.dataset.seatPromotion || "").trim()).filter(Boolean),
    )];
    purchasePromotions.hidden = promotions.length === 0;
    purchasePromotionsList.textContent = promotions.join(" · ");
  }

  if (purchaseButton && requiresSeatSelection && !purchaseSubmitting && !purchasePreparing) {
    purchaseButton.disabled = !quantityValid || seatStateUpdating;
    purchaseButton.classList.toggle("is-processing", seatStateUpdating && selectedCount > 0);
    purchaseButton.setAttribute("aria-busy", String(seatStateUpdating && selectedCount > 0));
    if (selectedCount === 0) {
      purchaseButton.textContent = purchaseButton.dataset.selectSeatLabel;
    } else if (seatStateUpdating) {
      purchaseButton.innerHTML = '<span class="purchase-loading-clock" aria-hidden="true"></span>Actualizando butacas…';
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

document.addEventListener("candy:change", updateSeatDrivenPurchaseState);

document.querySelectorAll("button.client-seat").forEach((seat) => {
  seat.addEventListener("click", () => {
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

    if (seat.classList.contains("is-selected")) {
      seat.classList.remove("is-selected");
      queueSeatReservation(seat, "release", true);
    } else {
      seat.classList.add("is-selected");
      queueSeatReservation(seat, "reserve");
    }
    serializeSelectedSeats(seatMap);
    updateSeatDrivenPurchaseState();
  });
});

seatMaps.forEach((seatMap) => {
  initializeSeatMapViewport(seatMap);
  syncSeatStatus(seatMap);
  window.setInterval(() => syncSeatStatus(seatMap), refreshIntervalMs(seatMap));
});

purchaseForm?.addEventListener("submit", async (event) => {
  if (purchaseSubmitting || purchasePreparing) {
    event.preventDefault();
    return;
  }

  if (submitAfterReservationFlush) {
    submitAfterReservationFlush = false;
    purchaseSubmitting = true;
    setPurchaseProcessing(true);
    return;
  }

  const activeSeatMap = getActiveSeatMap();
  if (activeSeatMap && (selectedSeatsFor(activeSeatMap).length === 0 || (Number(activeSeatMap.dataset.requiredQuantity) && selectedSeatsFor(activeSeatMap).length !== Number(activeSeatMap.dataset.requiredQuantity)))) {
    event.preventDefault();
    updateSeatDrivenPurchaseState();
    return;
  }

  const hasPendingOperations = hasPendingSeatOperations(activeSeatMap);
  if (hasPendingOperations) {
    event.preventDefault();
    purchasePreparing = true;
    setPurchaseProcessing(true);
    try {
      await flushSeatReservations(activeSeatMap);
      purchasePreparing = false;
      if (selectedSeatsFor(activeSeatMap).length > 0) {
        purchaseButton.disabled = false;
        submitAfterReservationFlush = true;
        purchaseForm.requestSubmit();
      } else {
        purchaseButton.classList.remove("is-processing");
        purchaseButton.removeAttribute("aria-busy");
        updateSeatDrivenPurchaseState();
      }
    } catch (error) {
      purchasePreparing = false;
      purchaseButton.classList.remove("is-processing");
      purchaseButton.removeAttribute("aria-busy");
      updateSeatDrivenPurchaseState();
      showReservationError(error);
    }
    return;
  }

  purchaseSubmitting = true;
  setPurchaseProcessing(true);
});
