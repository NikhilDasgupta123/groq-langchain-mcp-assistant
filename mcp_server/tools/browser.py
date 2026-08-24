from __future__ import annotations

import ipaddress
import socket
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    TimeoutError as PlaywrightTimeoutError,
    async_playwright,
)


_playwright: Optional[Playwright] = None
_browser: Optional[Browser] = None
_context: Optional[BrowserContext] = None
_page: Optional[Page] = None

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCREENSHOT_DIR = PROJECT_ROOT / "static" / "browser"
SCREENSHOT_FILE = SCREENSHOT_DIR / "latest.png"


def _validate_url(url: str) -> str:
    parsed = urlparse(url)

    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Only http:// and https:// URLs are allowed.")

    if not parsed.hostname:
        raise ValueError("URL must contain a valid hostname.")

    hostname = parsed.hostname.lower()

    if hostname in {"localhost", "localhost.localdomain"}:
        raise ValueError("Localhost URLs are not allowed.")

    try:
        addresses = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise ValueError(f"Unable to resolve hostname: {hostname}") from exc

    for address in addresses:
        ip_text = address[4][0]

        try:
            ip = ipaddress.ip_address(ip_text)
        except ValueError:
            continue

        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise ValueError("Private or local-network URLs are not allowed.")

    return url


async def _get_page() -> Page:
    global _playwright
    global _browser
    global _context
    global _page

    if _context is not None:
        open_pages = [
            page
            for page in _context.pages
            if not page.is_closed()
        ]

        if open_pages:
            _page = open_pages[-1]
            return _page

    if _playwright is None:
        _playwright = await async_playwright().start()

    if _browser is None:
        _browser = await _playwright.chromium.launch(
            headless=True,
        )

    if _context is None:
        _context = await _browser.new_context(
            viewport={
                "width": 1440,
                "height": 1000,
            },
        )

    _page = await _context.new_page()
    _page.set_default_timeout(10000)

    return _page


async def _refresh_active_page(page: Page) -> Page:
    """
    If a click opened a new tab/window, automatically switch to the newest page.
    """
    global _page

    await page.wait_for_timeout(350)

    if _context is not None:
        open_pages = [
            candidate
            for candidate in _context.pages
            if not candidate.is_closed()
        ]

        if open_pages:
            _page = open_pages[-1]
            page = _page

    try:
        await page.wait_for_load_state(
            "domcontentloaded",
            timeout=5000,
        )
    except PlaywrightTimeoutError:
        pass

    return page


async def _save_screenshot(page: Page) -> str:
    SCREENSHOT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    await page.screenshot(
        path=str(SCREENSHOT_FILE),
        full_page=False,
    )

    return "/static/browser/latest.png"


async def _page_state(page: Page) -> dict:
    screenshot_url = await _save_screenshot(page)

    return {
        "url": page.url,
        "title": await page.title(),
        "screenshot_url": screenshot_url,
    }



async def _visible_dialog_count(page: Page) -> int:
    """
    Count common visible modal/dialog containers so popup dismissal can be
    verified instead of claiming success only because a click was attempted.
    """
    selectors = [
        "[role='dialog']",
        "[aria-modal='true']",
        ".modal",
        "[class*='modal' i]",
        "[class*='popup' i]",
    ]

    count = 0

    for selector in selectors:
        locator = page.locator(selector)

        try:
            total = await locator.count()
        except Exception:
            continue

        for index in range(min(total, 20)):
            try:
                if await locator.nth(index).is_visible():
                    count += 1
            except Exception:
                continue

    return count


async def _try_click(locator) -> bool:
    try:
        if await locator.count() < 1:
            return False

        target = locator.first

        if not await target.is_visible():
            return False

        await target.click(timeout=2500)
        return True

    except Exception:
        return False

def register_browser_tools(mcp):

    @mcp.tool()
    async def browser_open_url(url: str) -> dict:
        """
        Open a public HTTP(S) website in the persistent Playwright browser.

        The page remains open across later chat messages because the MCP
        server/session is kept alive by FastAPI.
        """
        safe_url = _validate_url(url)
        page = await _get_page()

        await page.goto(
            safe_url,
            wait_until="domcontentloaded",
            timeout=20000,
        )

        return {
            "status": "opened",
            **await _page_state(page),
        }


    @mcp.tool()
    async def browser_get_title() -> dict:
        """Get the current page title and URL."""
        page = await _get_page()

        return await _page_state(page)


    @mcp.tool()
    async def browser_get_page_text(
        max_chars: int = 5000,
    ) -> dict:
        """Read visible text from the current browser page."""
        page = await _get_page()

        text = await page.locator("body").inner_text(
            timeout=10000,
        )

        return {
            **await _page_state(page),
            "text": text[:max_chars],
        }


    @mcp.tool()
    async def browser_get_interactive_elements(
        max_items: int = 80,
    ) -> dict:
        """
        Inspect visible buttons, links, inputs and accessible controls.

        Use this when the correct click/fill target is unclear instead of
        inventing a selector.
        """
        page = await _get_page()

        elements = page.locator(
            "button, a, input, textarea, select, "
            "[role='button'], [role='link'], "
            "[aria-label], [title]"
        )

        count = min(
            await elements.count(),
            max_items,
        )

        items = []

        for index in range(count):
            element = elements.nth(index)

            try:
                if not await element.is_visible():
                    continue

                tag = await element.evaluate(
                    "(el) => el.tagName.toLowerCase()"
                )

                try:
                    text = (
                        await element.inner_text(timeout=1000)
                    ).strip()
                except Exception:
                    text = ""

                items.append(
                    {
                        "index": index,
                        "tag": tag,
                        "text": text[:200],
                        "role": await element.get_attribute("role"),
                        "aria_label": await element.get_attribute("aria-label"),
                        "placeholder": await element.get_attribute("placeholder"),
                        "title": await element.get_attribute("title"),
                        "name": await element.get_attribute("name"),
                        "type": await element.get_attribute("type"),
                    }
                )

            except Exception:
                continue

        return {
            **await _page_state(page),
            "elements": items,
        }


    @mcp.tool()
    async def browser_click_text(
        text: str,
        exact: bool = False,
    ) -> dict:
        """
        Click a visible element using its text.
        """
        page = await _get_page()

        locator = page.get_by_text(
            text,
            exact=exact,
        ).first

        await locator.click(
            timeout=10000,
        )

        page = await _refresh_active_page(page)

        return {
            "status": "clicked",
            "method": "text",
            "target": text,
            **await _page_state(page),
        }


    @mcp.tool()
    async def browser_click_role(
        role: str,
        name: str | None = None,
        exact: bool = False,
    ) -> dict:
        """
        Click an element by accessibility role and optional accessible name.

        Examples:
        role='button', name='Close'
        role='button', name='Search'
        role='link', name='Login'
        """
        page = await _get_page()

        kwargs = {}

        if name:
            kwargs["name"] = name
            kwargs["exact"] = exact

        locator = page.get_by_role(
            role,
            **kwargs,
        ).first

        await locator.click(
            timeout=10000,
        )

        page = await _refresh_active_page(page)

        return {
            "status": "clicked",
            "method": "role",
            "role": role,
            "name": name,
            **await _page_state(page),
        }


    @mcp.tool()
    async def browser_click(
        by: str,
        value: str,
        timeout: int = 10,
    ) -> dict:
        """
        Click an element using a locator strategy.

        Supported `by`:
        css, css selector, xpath, text, role, placeholder, label, testid.
        """
        page = await _get_page()
        page.set_default_timeout(timeout * 1000)

        strategy = by.lower().strip().replace("_", " ")

        if strategy in {
            "css",
            "css selector",
            "selector",
        }:
            locator = page.locator(value)

        elif strategy == "xpath":
            locator = page.locator(
                f"xpath={value}"
            )

        elif strategy == "text":
            locator = page.get_by_text(value)

        elif strategy == "role":
            locator = page.get_by_role(value)

        elif strategy == "placeholder":
            locator = page.get_by_placeholder(value)

        elif strategy == "label":
            locator = page.get_by_label(value)

        elif strategy in {
            "testid",
            "test id",
        }:
            locator = page.get_by_test_id(value)

        else:
            raise ValueError(
                "Unsupported locator strategy. "
                "Use css, xpath, text, role, placeholder, label, or testid."
            )

        await locator.first.click()

        page = await _refresh_active_page(page)

        return {
            "status": "clicked",
            "method": strategy,
            "target": value,
            **await _page_state(page),
        }


    @mcp.tool()
    async def browser_fill(
        value: str,
        text: str,
        by: str = "placeholder",
        clear_first: bool = True,
    ) -> dict:
        """
        Fill an input field.

        Supported `by`:
        placeholder, label, css, css selector, xpath.
        """
        page = await _get_page()

        strategy = by.lower().strip().replace("_", " ")

        if strategy == "placeholder":
            locator = page.get_by_placeholder(value)

        elif strategy == "label":
            locator = page.get_by_label(value)

        elif strategy in {
            "css",
            "css selector",
            "selector",
        }:
            locator = page.locator(value)

        elif strategy == "xpath":
            locator = page.locator(
                f"xpath={value}"
            )

        else:
            raise ValueError(
                "Unsupported fill locator. "
                "Use placeholder, label, css, or xpath."
            )

        locator = locator.first

        if clear_first:
            await locator.fill(text)
        else:
            await locator.press_sequentially(text)

        return {
            "status": "filled",
            "method": strategy,
            "target": value,
            "text": text,
            **await _page_state(page),
        }


    @mcp.tool()
    async def browser_type_text(
        by: str,
        value: str,
        text: str,
        clear_first: bool = True,
        timeout: int = 10,
    ) -> dict:
        """
        Compatibility tool for earlier MCP browser prompts.
        """
        page = await _get_page()
        page.set_default_timeout(timeout * 1000)

        strategy = by.lower().strip().replace("_", " ")

        if strategy in {
            "css",
            "css selector",
            "selector",
        }:
            locator = page.locator(value)

        elif strategy == "xpath":
            locator = page.locator(
                f"xpath={value}"
            )

        elif strategy == "placeholder":
            locator = page.get_by_placeholder(value)

        elif strategy == "label":
            locator = page.get_by_label(value)

        else:
            raise ValueError(
                "Unsupported typing locator. "
                "Use css, xpath, placeholder, or label."
            )

        locator = locator.first

        if clear_first:
            await locator.fill(text)
        else:
            await locator.press_sequentially(text)

        return {
            "status": "typed",
            "method": strategy,
            "target": value,
            **await _page_state(page),
        }


    @mcp.tool()
    async def browser_press(
        key: str,
    ) -> dict:
        """
        Press a keyboard key on the active page.

        Examples: Enter, Escape, Tab, ArrowDown.
        """
        page = await _get_page()

        await page.keyboard.press(key)

        page = await _refresh_active_page(page)

        return {
            "status": "pressed",
            "key": key,
            **await _page_state(page),
        }


    @mcp.tool()
    async def browser_dismiss_popup() -> dict:
        """
        Dismiss the currently visible popup, modal, dialog, login box, or overlay.

        Use this when the user says things such as:
        - close the popup
        - close the login box
        - dismiss this dialog
        - remove this overlay

        Do NOT use browser_close_session for those requests.
        """
        page = await _get_page()

        if page.url == "about:blank":
            return {
                "status": "not_dismissed",
                "reason": "No website is currently open.",
                **await _page_state(page),
            }

        before_dialogs = await _visible_dialog_count(page)

        # Prefer explicit accessible close controls.
        candidates = [
            page.get_by_role("button", name="Close", exact=False),
            page.get_by_role("button", name="Dismiss", exact=False),
            page.get_by_role("button", name="Cancel", exact=False),
            page.get_by_role("button", name="Not now", exact=False),
            page.locator("[aria-label*='close' i]"),
            page.locator("[title*='close' i]"),
            page.locator("button:has-text('✕')"),
            page.locator("button:has-text('×')"),
            page.locator("button:has-text('X')"),
            page.locator("[role='dialog'] button").filter(has_text="✕"),
            page.locator("[role='dialog'] button").filter(has_text="×"),
        ]

        clicked = False
        method = None

        for candidate in candidates:
            if await _try_click(candidate):
                clicked = True
                method = "close_control"
                break

        if clicked:
            await page.wait_for_timeout(400)

            after_dialogs = await _visible_dialog_count(page)

            # A click on a visible close control is considered confirmed if the
            # dialog count decreased, or if there were no detectable semantic
            # dialogs to begin with.
            if before_dialogs == 0 or after_dialogs < before_dialogs:
                return {
                    "status": "dismissed",
                    "method": method,
                    **await _page_state(page),
                }

        # Escape is a safe generic fallback for many dialogs.
        try:
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(400)
        except Exception:
            pass

        after_escape_dialogs = await _visible_dialog_count(page)

        if before_dialogs > 0 and after_escape_dialogs < before_dialogs:
            return {
                "status": "dismissed",
                "method": "escape",
                **await _page_state(page),
            }

        # Final generic fallback: look for a visible X-like control anywhere.
        x_like = page.locator(
            "button, [role='button'], span, div"
        ).filter(
            has_text="✕"
        )

        if await _try_click(x_like):
            await page.wait_for_timeout(400)

            return {
                "status": "dismissed",
                "method": "visible_x",
                **await _page_state(page),
            }

        return {
            "status": "not_dismissed",
            "reason": (
                "No reliable visible close control was found. "
                "Inspect interactive elements before trying another action."
            ),
            **await _page_state(page),
        }



    @mcp.tool()
    async def browser_screenshot() -> dict:
        """Capture the current browser viewport."""
        page = await _get_page()

        return {
            "status": "captured",
            **await _page_state(page),
        }


    @mcp.tool()
    async def browser_close_session() -> dict:
        """
        Close the entire Playwright browser session.

        Use ONLY when the user explicitly asks to close/quit/end the browser
        session itself. Never use this for a popup, modal, login box, or dialog.
        """
        global _playwright
        global _browser
        global _context
        global _page

        if _page is not None:
            try:
                await _page.close()
            except Exception:
                pass

        if _context is not None:
            try:
                await _context.close()
            except Exception:
                pass

        if _browser is not None:
            try:
                await _browser.close()
            except Exception:
                pass

        if _playwright is not None:
            try:
                await _playwright.stop()
            except Exception:
                pass

        _page = None
        _context = None
        _browser = None
        _playwright = None

        if SCREENSHOT_FILE.exists():
            SCREENSHOT_FILE.unlink()

        return {
            "status": "closed"
        }
