"""Dashboard: numbers."""


def percentage(part, total):
    return float(part) * 100 / float(total) if total else 0


def css_percentage(value):
    return f"{max(min(value, 100), 0):.2f}%"
