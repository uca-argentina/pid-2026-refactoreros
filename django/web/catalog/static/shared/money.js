export function formatMoney(value) {
  return value.toLocaleString("es-AR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

export function formatCurrency(value) {
  return new Intl.NumberFormat("es-AR", {style: "currency", currency: "ARS"}).format(value);
}

export function parseSeatPrice(rawValue) {
  const rawPrice = String(rawValue || "").trim();
  const normalizedPrice = rawPrice.includes(",")
    ? rawPrice.replace(/\./g, "").replace(",", ".")
    : rawPrice;
  const price = Number(normalizedPrice);
  return Number.isFinite(price) ? price : null;
}
