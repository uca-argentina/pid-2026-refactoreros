"""Coordenadas compartidas por planos, cotizaciones y comprobantes."""

import re


def index_to_letters(index):
    label = ""
    value = index + 1
    while value > 0:
        value, remainder = divmod(value - 1, 26)
        label = chr(65 + remainder) + label
    return label


def snapshot_seats(snapshot):
    """Admite snapshots históricos (lista) y actuales (objeto con dimensiones)."""
    return snapshot.get("seats", []) if isinstance(snapshot, dict) else snapshot or []


def seat_labels(snapshot):
    seats = snapshot_seats(snapshot)
    columns = {
        column: index_to_letters(index)
        for index, column in enumerate(sorted({seat["column"] for seat in seats}))
    }
    return {f"{seat['row'] + 1}{columns[seat['column']]}": seat for seat in seats}


def summarize_seats(labels, *, row_title="fila", separator="; "):
    grouped, fallback = {}, []
    for label in labels:
        match = re.fullmatch(r"(\d+)([A-Z]+)", label)
        if not match:
            fallback.append(label)
            continue
        row, column = match.groups()
        grouped.setdefault(row, []).append(column)
    groups = []
    for row in sorted(grouped, key=int):
        columns = sorted(grouped[row], key=lambda value: (len(value), value))
        text = columns[0] if len(columns) == 1 else f"{', '.join(columns[:-1])} y {columns[-1]}"
        word = "asiento" if len(columns) == 1 else "asientos"
        groups.append(f"{row_title} {row}, {word} {text}")
    return separator.join(groups + fallback)
