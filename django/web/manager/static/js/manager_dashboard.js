(function () {
  var dashboard = document.querySelector("[data-dashboard]");
  if (!dashboard) return;
  var status = document.getElementById("dashboard-status");
  var pendingRequest;
  var requestNumber = 0;
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

  function updateHeatmapOverflow() {
    var scroll = dashboard.querySelector(".heatmap-scroll");
    var hint = dashboard.querySelector("[data-heatmap-overflow-hint]");
    if (scroll && hint) hint.hidden = scroll.scrollWidth <= scroll.clientWidth + 1;
  }

  function showTooltip(target, x, y) {
    value.textContent = target.dataset.tipValue || "";
    title.textContent = target.dataset.tipTitle || "";
    meta.textContent = target.dataset.tipMeta || "";
    meta.hidden = !target.dataset.tipMeta;
    tooltip.hidden = false;
    var rect = tooltip.getBoundingClientRect();
    var left = Math.min(x + 14, window.innerWidth - rect.width - 8);
    var top = y - rect.height - 12;
    if (top < 8) {
      top = y + 18;
    }
    tooltip.style.left = Math.max(8, left) + "px";
    tooltip.style.top = Math.max(8, Math.min(top, window.innerHeight - rect.height - 8)) + "px";
  }

  function hideTooltip() {
    tooltip.hidden = true;
  }

  function focusTarget(key) {
    return Array.from(dashboard.querySelectorAll("[data-focus-key]")).find(function (element) {
      return element.dataset.focusKey === key;
    });
  }

  async function navigate(url, options) {
    options = options || {};
    var currentRequest = ++requestNumber;
    if (pendingRequest) pendingRequest.abort();
    pendingRequest = new AbortController();
    var controller = pendingRequest;
    var timeout = window.setTimeout(function () { controller.abort(); }, 15000);
    var openTables = Array.from(dashboard.querySelectorAll("details")).map(function (detail) {
      return detail.open;
    });
    var heatmap = dashboard.querySelector(".heatmap-scroll");
    var heatmapScroll = heatmap ? heatmap.scrollLeft : 0;
    var scrollY = window.scrollY;
    var scrollX = window.scrollX;
    hideTooltip();
    dashboard.setAttribute("aria-busy", "true");
    dashboard.classList.add("is-updating");
    status.textContent = "Actualizando los resultados de la selección…";

    try {
      var response = await fetch(url, { signal: controller.signal, credentials: "same-origin" });
      if (!response.ok) throw new Error("Dashboard unavailable");
      var html = await response.text();
      if (currentRequest !== requestNumber) return;
      var page = new DOMParser().parseFromString(html, "text/html");
      var updated = page.querySelector("[data-dashboard]");
      if (!updated) throw new Error("Dashboard missing");
      dashboard.replaceChildren.apply(dashboard, Array.from(updated.childNodes));
      if (options.push !== false) window.history.pushState(null, "", url);
      dashboard.querySelectorAll("details").forEach(function (detail, index) {
        detail.open = Boolean(openTables[index]);
      });
      var newHeatmap = dashboard.querySelector(".heatmap-scroll");
      if (newHeatmap) newHeatmap.scrollLeft = heatmapScroll;
      if (window.lucide) window.lucide.createIcons();
      updateHeatmapOverflow();

      var target = options.key ? focusTarget(options.key) : null;
      window.scrollTo(scrollX, scrollY);
      if (target && options.top !== undefined) {
        window.scrollBy(0, target.getBoundingClientRect().top - options.top);
      }
      if (options.keyboard) {
        if (!target) target = dashboard.querySelector(".dashboard-clear, .period-option.is-active");
        if (target) target.focus({ preventScroll: true });
      }
      var filters = Array.from(dashboard.querySelectorAll(".dashboard-filter-chip > span")).map(function (chip) {
        return chip.textContent.trim();
      });
      var values = Array.from(dashboard.querySelectorAll(".kpi-value")).map(function (kpi) {
        return kpi.textContent.trim();
      });
      status.textContent = (filters.length ? "Filtros: " + filters.join(". ") + ". " : "Filtros borrados. ") +
        "Resultados actualizados. Recaudación: " + values[0] + ". Entradas vendidas: " + values[1] + ".";
    } catch (error) {
      if (currentRequest === requestNumber) window.location.assign(url);
    } finally {
      window.clearTimeout(timeout);
      if (currentRequest === requestNumber) {
        dashboard.removeAttribute("aria-busy");
        dashboard.classList.remove("is-updating");
        pendingRequest = null;
      }
    }
  }

  dashboard.addEventListener("click", function (event) {
    var link = event.target.closest("a[data-dashboard-link]");
    if (!link || event.defaultPrevented || event.button !== 0 ||
        event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    navigate(link.href, {
      key: link.dataset.focusKey,
      top: link.dataset.focusKey ? link.getBoundingClientRect().top : undefined,
      keyboard: event.detail === 0
    });
  });

  dashboard.addEventListener("submit", function (event) {
    var form = event.target.closest("[data-dashboard-form]");
    if (!form) return;
    event.preventDefault();
    var url = new URL(form.action || window.location.href);
    url.search = new URLSearchParams(new FormData(form)).toString();
    navigate(url.href, { keyboard: true });
  });

  dashboard.addEventListener("pointermove", function (event) {
    var target = event.target.closest("[data-tip-value]");
    if (target && event.pointerType !== "touch" && !pendingRequest) {
      showTooltip(target, event.clientX, event.clientY);
    } else {
      hideTooltip();
    }
  });
  dashboard.addEventListener("pointerleave", hideTooltip);
  dashboard.addEventListener("focusin", function (event) {
    var target = event.target.closest("[data-tip-value]");
    if (!target || pendingRequest) return;
    var rect = target.getBoundingClientRect();
    showTooltip(target, rect.left + rect.width / 2, rect.top);
  });
  dashboard.addEventListener("focusout", hideTooltip);
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") {
      hideTooltip();
    }
  });
  window.addEventListener("scroll", hideTooltip, { passive: true });
  window.addEventListener("resize", updateHeatmapOverflow);
  window.addEventListener("popstate", function () {
    navigate(window.location.href, { push: false });
  });
  updateHeatmapOverflow();
})();
