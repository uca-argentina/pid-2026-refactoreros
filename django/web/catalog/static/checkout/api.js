export function createReservationApi({csrfToken, markUnavailableSeats, applyReservationState, syncSeatStatus}) {
  async function requestSingleSeatReservation(seat, action) {
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
    return payload;
  }

  async function sendSeatOperations(seatMap, operations) {
    const batchUrl = seatMap?.dataset.reservationBatchUrl;
    if (!batchUrl) {
      const processed = [];
      for (const operation of operations) {
        const seat = seatMap.querySelector(`[data-seat-label="${operation.label}"]`);
        await requestSingleSeatReservation(seat, operation.action);
        processed.push(operation);
      }
      await syncSeatStatus(seatMap);
      return {ok: true, processed};
    }

    const response = await fetch(batchUrl, {
      method: "POST",
      headers: {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken(),
      },
      body: JSON.stringify({operations}),
    });
    const payload = await response.json().catch(() => ({}));
    if (payload.unavailable || payload.reserved) {
      applyReservationState(seatMap, payload);
    }
    if (!response.ok || !payload.ok) {
      const firstError = (payload.errors || [])[0]?.error;
      throw new Error(firstError || payload.error || "Algunas butacas ya no estan disponibles.");
    }
    return payload;
  }
  return {sendSeatOperations};
}
