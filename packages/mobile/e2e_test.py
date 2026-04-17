"""
E2E test: spins up a fresh kaydet server + uses running Expo web (localhost:8081),
then uses Playwright to verify that #tags and key:value tokens are highlighted.

Run (with expo already running on :8081):
  uv run python packages/mobile/e2e_test.py
"""

from __future__ import annotations

import secrets
import sys
import tempfile
import threading
import time
from configparser import ConfigParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "core" / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "server" / "src"))

from kaydet_core import database
from kaydet_core.service import KaydetService
from kaydet_server.http_server import start_http_server


def make_test_server(tmp: Path, port: int):
    storage = tmp / "storage"
    storage.mkdir()
    config_dir = tmp / "config"
    config_dir.mkdir()
    db_path = tmp / "index.db"

    conn = database.get_db_connection(db_path, check_same_thread=False)
    database.initialize_database(conn)

    cp = ConfigParser(interpolation=None)
    cp["SETTINGS"] = {
        "DAY_FILE_PATTERN": "%Y-%m-%d.txt",
        "DAY_TITLE_PATTERN": "%Y/%m/%d/ - %A",
        "STORAGE_DIR": str(storage),
        "EDITOR": "cat",
        "sync_token": "0",
        "DEVICE_PREFIX": "t",
        "LAST_ID": "0",
    }

    service = KaydetService(
        config=cp["SETTINGS"],
        config_dir=config_dir,
        storage_dir=storage,
        conn=conn,
    )

    api_key = "kyd_test_" + secrets.token_hex(8)
    conn.execute(
        "INSERT INTO sync_keys (key, name, created_at) VALUES (?, ?, datetime('now'))",
        (api_key, "test"),
    )
    conn.commit()

    thread = threading.Thread(
        target=start_http_server,
        args=(conn, storage, cp["SETTINGS"], config_dir, "127.0.0.1", port),
        daemon=True,
    )
    thread.start()
    time.sleep(1)

    return service, api_key


def run_test():
    from playwright.sync_api import sync_playwright

    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        port = 18484

        print("Starting test kaydet server on :18484 ...")
        service, api_key = make_test_server(tmp, port)

        # Seed entries
        r1 = service.add_entry(text="test entry #kaydet price:300")
        r2 = service.add_entry(text="hello world no tokens here")
        r3 = service.add_entry(text="multiple #tags and key:value pairs mood:happy")
        assert r1["success"] and r2["success"] and r3["success"]
        print(f"Seeded entries: {r1['entry_id']}, {r2['entry_id']}, {r3['entry_id']}")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)  # visible for debugging
            context = browser.new_context()
            page = context.new_page()

            console_logs: list[str] = []
            page.on("console", lambda msg: console_logs.append(f"[{msg.type}] {msg.text}"))

            print("Opening app...")
            page.goto("http://localhost:8081")
            page.wait_for_load_state("networkidle", timeout=15000)

            # Inject test server config using the exact AsyncStorage keys storage.ts uses
            page.evaluate(f"""() => {{
                localStorage.setItem('kaydet_server_url', 'http://localhost:{port}');
                localStorage.setItem('kaydet_api_key', '{api_key}');
                localStorage.setItem('kaydet_sync_token', '0');
                localStorage.removeItem('kaydet_entries');
            }}""")

            # Verify keys were set before reloading
            stored = page.evaluate("""() => ({
                serverUrl: localStorage.getItem('kaydet_server_url'),
                apiKey: localStorage.getItem('kaydet_api_key'),
                syncToken: localStorage.getItem('kaydet_sync_token'),
            })""")
            print(f"localStorage after inject: {stored}")

            page.reload()
            page.wait_for_load_state("networkidle", timeout=15000)
            # Wait for app to finish initial auto-sync (triggered on load when configured)
            time.sleep(6)

            print("\n── Console logs after load ──")
            for log in console_logs:
                print(log)
            console_logs.clear()

            page.screenshot(path="/tmp/kaydet_e2e_1_loaded.png")
            print("Screenshot: /tmp/kaydet_e2e_1_loaded.png")

            # Click sync and wait for "Sync" button to reappear (not "…")
            sync_btn = page.locator("text=Sync").first
            sync_btn.click()
            # Wait for sync to finish: button goes "…" then back to "Sync"
            page.wait_for_selector("text=Sync", timeout=15000)
            time.sleep(1)  # brief settle

            print("\n── Console logs after sync ──")
            for log in console_logs:
                print(log)
            console_logs.clear()

            page.screenshot(path="/tmp/kaydet_e2e_2_synced.png")
            print("Screenshot: /tmp/kaydet_e2e_2_synced.png")

            # Check page HTML for tokens
            content = page.content()

            checks = [
                ("#kaydet", "#kaydet in page content"),
                ("price:300", "price:300 in page content"),
                ("mood:happy", "mood:happy in page content"),
            ]
            print("\n── Token checks ──")
            for token, label in checks:
                found = token in content
                print(f"{'✓' if found else '✗'} {label}")

            # Click on entry with #kaydet to open detail
            entry = page.locator("text=#kaydet").first
            if entry.is_visible():
                color = entry.evaluate("el => getComputedStyle(el).color")
                print(f"\n#kaydet color: {color}")

            # ── Swipe debug ──
            print("\n── Swipe debug ──")
            # Find first card and simulate swipe left via mouse drag
            card = page.locator("text=#kaydet").first
            box = card.bounding_box()
            print(f"Card bounding box: {box}")

            if box:
                cx = box["x"] + box["width"] / 2
                cy = box["y"] + box["height"] / 2
                # Drag from right side to left to reveal swipe actions
                page.mouse.move(cx + 100, cy)
                page.mouse.down()
                page.mouse.move(cx - 80, cy, steps=20)
                page.mouse.up()
                time.sleep(1)

                page.screenshot(path="/tmp/kaydet_e2e_3_swiped.png")
                print("Screenshot after swipe: /tmp/kaydet_e2e_3_swiped.png")

                # Check if Delete button is visible
                delete_btn = page.locator("text=Delete").first
                edit_btn = page.locator("text=Edit").first
                print(f"Delete visible: {delete_btn.is_visible()}")
                print(f"Edit visible: {edit_btn.is_visible()}")

                if delete_btn.is_visible():
                    print("Clicking Delete...")
                    network_requests: list[str] = []
                    page.on("request", lambda req: network_requests.append(f"{req.method} {req.url}"))
                    delete_btn.click()
                    time.sleep(2)
                    print(f"Network requests after Delete click: {network_requests}")
                    page.screenshot(path="/tmp/kaydet_e2e_4_after_delete.png")
                    print("Screenshot after delete: /tmp/kaydet_e2e_4_after_delete.png")

                    # Check console logs
                    print("\n── Console logs after delete ──")
                    for log in console_logs:
                        print(log)

            browser.close()

        print("\nDone.")


if __name__ == "__main__":
    run_test()
