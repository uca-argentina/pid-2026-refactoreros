"""Recorrida real sobre las cuentas de práctica; bloquea toda conexión externa.

Uso: python scripts/smoke_browser.py --base-url http://localhost:8001
Requiere playwright y Chromium previamente instalados. Genera una compra local.
"""

import argparse
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright, expect


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8001")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    if urlparse(base).hostname not in {"localhost", "127.0.0.1"}:
        parser.error("Esta prueba solo permite un servidor local con datos de práctica.")
    artifacts = Path(__file__).resolve().parent.parent / "artifacts"
    artifacts.mkdir(exist_ok=True)
    errors, external, failed = [], [], []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1366, "height": 900})

        def local_only(route):
            if urlparse(route.request.url).hostname not in {"localhost", "127.0.0.1"}:
                external.append(route.request.url)
                route.abort()
            else:
                route.continue_()

        context.route("**/*", local_only)
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on(
            "response",
            lambda response: failed.append((response.status, response.url))
            if response.status >= 400
            else None,
        )

        def visit(path):
            response = page.goto(base + path, wait_until="networkidle")
            assert response.status == 200, (path, response.status)

        def login(email):
            visit("/login/")
            page.locator('[name="username"]').fill(email)
            page.locator('[name="password"]').fill("PracticaLocal2026!")
            page.locator('.auth-form button[type="submit"]').click()
            page.wait_for_load_state("networkidle")
            assert "/login/" not in page.url, page.url

        login("cliente@local.test")
        page.screenshot(path=str(artifacts / "catalogo.png"), full_page=True)
        page.locator('a[href^="/peliculas/"]').first.click()
        page.locator(".screening-time-chip").first.click()
        page.wait_for_load_state("networkidle")
        seat = page.locator("button.client-seat:not(:disabled)").first
        seat.click()
        buy = page.locator('.purchase-action button[type="submit"]')
        expect(buy).to_be_enabled(timeout=15000)
        expect(page.locator('[name="selected_seats"]')).not_to_have_value("")
        page.screenshot(path=str(artifacts / "checkout.png"), full_page=True)
        buy.click()
        page.wait_for_url("**/mis-entradas/")
        visit("/mis-entradas/")
        page.locator(".ticket-detail-link, .ticket-qr-link").first.click()
        page.wait_for_load_state("networkidle")
        expect(page.locator("[data-qr-payload] canvas")).to_have_count(1)
        if page.locator(".ticket-reprogram-screening").count():
            page.locator(".ticket-reprogram-screening").click()
            page.locator(".screening-time-chip").first.click()
            page.wait_for_load_state("networkidle")
            page.locator("button.client-seat:not(:disabled)").first.click()
            confirm = page.locator('.purchase-action button[type="submit"]')
            expect(confirm).to_be_enabled(timeout=15000)
            confirm.click()
            page.wait_for_url("**/mis-entradas/")
        visit("/candy/")
        expect(page.locator("[data-candy-store-form]")).to_have_count(1)
        page.locator('[data-candy-step="1"]:not(:disabled)').first.click()
        page.locator("[data-candy-buy]").click()
        page.wait_for_url("**/candy/pedidos/*/")
        expect(page.locator("[data-qr-payload] canvas")).to_have_count(1)
        visit("/juegos/premios/")
        page.set_viewport_size({"width": 390, "height": 844})
        visit("/")
        page.screenshot(path=str(artifacts / "cliente-mobile.png"), full_page=True)
        page.locator(".client-logout-link").click()
        page.wait_for_url("**/login/")

        page.set_viewport_size({"width": 1366, "height": 900})
        login("gerente@local.test")
        for path in (
            "/gestion/",
            "/gestion/dashboard/",
            "/gestion/dashboard/?view=candy",
            "/gestion/salas/nueva/",
            "/gestion/funciones/",
            "/gestion/configuracion/",
        ):
            visit(path)
            if path == "/gestion/salas/nueva/":
                expect(page.locator(".seat_checkbox").first).to_be_attached()
                expect(page.locator(".celda-checkbox").first).to_be_visible()
        visit("/gestion/dashboard/")
        page.screenshot(path=str(artifacts / "dashboard.png"), full_page=True)
        browser.close()
    assert not external, f"Dependencias externas: {external}"
    assert not errors, f"Errores JavaScript: {errors}"
    assert not failed, f"Respuestas fallidas: {failed}"
    print(
        "OK: compra, reprogramación, QR, candy, premios, logout, gestión y editor; sin conexiones externas ni errores JS/HTTP."
    )
    print(f"Capturas: {artifacts}")


if __name__ == "__main__":
    main()
