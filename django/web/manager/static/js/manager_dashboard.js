(function () {
  var targets = document.querySelectorAll("[data-tip-value]");
  if (!targets.length) {
    return;
  }

  var tooltip = document.createElement("div");
  var value = document.createElement("strong");
  var title = document.createElement("span");
  var meta = document.createElement("span");
  tooltip.className = "viz-tooltip";
  tooltip.setAttribute("role", "tooltip");
  tooltip.hidden = true;
  meta.className = "viz-tooltip-meta";
  tooltip.append(value, title, meta);
  document.body.appendChild(tooltip);

  function place(x, y) {
    var rect = tooltip.getBoundingClientRect();
    var left = Math.min(x + 14, window.innerWidth - rect.width - 8);
    var top = y - rect.height - 12;
    if (top < 8) {
      top = y + 18;
    }
    tooltip.style.left = Math.max(8, left) + "px";
    tooltip.style.top = top + "px";
  }

  function show(target, x, y) {
    // Los textos vienen de datos cargados por usuarios: siempre textContent.
    value.textContent = target.dataset.tipValue || "";
    title.textContent = target.dataset.tipTitle || "";
    meta.textContent = target.dataset.tipMeta || "";
    meta.hidden = !target.dataset.tipMeta;
    tooltip.hidden = false;
    place(x, y);
  }

  function hide() {
    tooltip.hidden = true;
  }

  targets.forEach(function (target) {
    target.addEventListener("pointermove", function (event) {
      show(target, event.clientX, event.clientY);
    });
    target.addEventListener("pointerleave", hide);
    target.addEventListener("focus", function () {
      var rect = target.getBoundingClientRect();
      show(target, rect.left + rect.width / 2, rect.top);
    });
    target.addEventListener("blur", hide);
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") {
      hide();
    }
  });
  window.addEventListener("scroll", hide, { passive: true });
})();
