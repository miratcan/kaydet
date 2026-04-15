"""E2E: Create an entry via mobile UI, verify it appears in the list."""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import Page, expect


@pytest.fixture()
def configured_app(page: Page, expo_web: str, kaydet_server: dict):
    """Open the app and configure settings."""
    page.goto(expo_web)
    page.wait_for_load_state("networkidle")

    # Dismiss any alert dialogs and log console
    page.on("dialog", lambda d: d.accept())
    page.on("console", lambda msg: print(f"[browser] {msg.text}"))
    page.on("pageerror", lambda err: print(f"[browser error] {err}"))

    # Go to Settings
    page.get_by_text("Settings").click()
    page.wait_for_timeout(500)

    # Fill server URL
    url_input = page.get_by_placeholder("https://example.com")
    url_input.fill(kaydet_server["url"])

    # Fill API key
    key_input = page.get_by_placeholder("kyd_")
    key_input.fill(kaydet_server["api_key"])

    # Test connection
    page.get_by_text("Test Connection").click()
    expect(page.get_by_text("Connected")).to_be_visible(
        timeout=10000
    )

    # Go back to list
    page.get_by_text("Done").click()
    page.wait_for_timeout(1000)

    return page


def _capture_entry(page: Page, text: str) -> None:
    """Helper: open capture, type text, save, wait for list."""
    page.get_by_text("+", exact=True).click()
    page.wait_for_timeout(500)

    textarea = page.get_by_placeholder("What's on your mind?")
    textarea.fill(text)

    page.get_by_text("Save").click()

    # Wait for Capture title to disappear (= returned to list)
    expect(page.get_by_text("Capture")).to_be_hidden(
        timeout=15000
    )
    # Wait for sync to finish
    page.wait_for_timeout(5000)


class TestCaptureAndList:
    def test_create_entry_appears_in_list(
        self, configured_app: Page
    ):
        """Push an entry and verify it shows up after sync."""
        page = configured_app

        _capture_entry(page, "Playwright e2e test entry #test")

        expect(
            page.get_by_text("Playwright e2e test entry")
        ).to_be_visible(timeout=10000)

    def test_entry_shows_tag(self, configured_app: Page):
        """Tags in entry text should appear as tag chips."""
        page = configured_app

        _capture_entry(page, "Meeting notes #work")

        expect(
            page.get_by_text("#work").first
        ).to_be_visible(timeout=10000)

    def test_settings_connection_test(
        self,
        page: Page,
        expo_web: str,
        kaydet_server: dict,
    ):
        """Settings screen: test connection shows Connected."""
        page.goto(expo_web)
        page.wait_for_load_state("networkidle")

        page.get_by_text("Settings").click()
        page.wait_for_timeout(500)

        page.get_by_placeholder("https://example.com").fill(
            kaydet_server["url"]
        )
        page.get_by_placeholder("kyd_").fill(
            kaydet_server["api_key"]
        )

        page.get_by_text("Test Connection").click()
        expect(page.get_by_text("Connected")).to_be_visible(
            timeout=10000
        )

    def test_settings_bad_key_shows_error(
        self,
        page: Page,
        expo_web: str,
        kaydet_server: dict,
    ):
        """Settings: wrong API key shows error."""
        page.goto(expo_web)
        page.wait_for_load_state("networkidle")

        page.get_by_text("Settings").click()
        page.wait_for_timeout(500)

        page.get_by_placeholder("https://example.com").fill(
            kaydet_server["url"]
        )
        page.get_by_placeholder("kyd_").fill("kyd_wrong_key")

        page.get_by_text("Test Connection").click()
        expect(
            page.get_by_text(
                re.compile(r"Invalid|error|fail", re.I)
            )
        ).to_be_visible(timeout=10000)

    def test_empty_list_message(
        self,
        page: Page,
        expo_web: str,
    ):
        """Unconfigured app shows empty state."""
        page.goto(expo_web)
        page.wait_for_load_state("networkidle")

        expect(
            page.get_by_text("No entries yet")
        ).to_be_visible(timeout=5000)
