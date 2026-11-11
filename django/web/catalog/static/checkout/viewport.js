export function updateSeatMapPanHints(seatMap) {
  const viewport = seatMap.querySelector("[data-seat-map-viewport]");
  if (!viewport) {
    return;
  }

  const maxScrollLeft = Math.max(viewport.scrollWidth - viewport.clientWidth, 0);
  const isCompactViewport = window.matchMedia("(max-width: 860px)").matches;
  const canPanLeft = isCompactViewport && viewport.scrollLeft > 1;
  const canPanRight = isCompactViewport && viewport.scrollLeft < maxScrollLeft - 1;
  seatMap.classList.toggle("can-pan-left", canPanLeft);
  seatMap.classList.toggle("can-pan-right", canPanRight);
  seatMap.querySelectorAll("[data-seat-map-pan]").forEach((button) => {
    button.disabled = button.dataset.seatMapPan === "left" ? !canPanLeft : !canPanRight;
  });
}

export function centerSeatMapViewport(seatMap) {
  const viewport = seatMap.querySelector("[data-seat-map-viewport]");
  if (!viewport || seatMap.dataset.viewportCentered) {
    return;
  }

  const maxScrollLeft = Math.max(viewport.scrollWidth - viewport.clientWidth, 0);
  viewport.scrollLeft = maxScrollLeft / 2;
  seatMap.dataset.viewportCentered = "true";
  updateSeatMapPanHints(seatMap);
}

export function initializeSeatMapViewport(seatMap) {
  const viewport = seatMap.querySelector("[data-seat-map-viewport]");
  if (!viewport) {
    return;
  }

  viewport.addEventListener("scroll", () => updateSeatMapPanHints(seatMap), {passive: true});
  seatMap.querySelectorAll("[data-seat-map-pan]").forEach((button) => {
    button.addEventListener("click", () => {
      const direction = button.dataset.seatMapPan === "left" ? -1 : 1;
      viewport.scrollBy({
        left: direction * viewport.clientWidth * 0.7,
        behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
      });
    });
  });
  window.requestAnimationFrame(() => centerSeatMapViewport(seatMap));

  if ("ResizeObserver" in window) {
    new ResizeObserver(() => updateSeatMapPanHints(seatMap)).observe(viewport);
  }
  window.addEventListener("resize", () => updateSeatMapPanHints(seatMap));
}
