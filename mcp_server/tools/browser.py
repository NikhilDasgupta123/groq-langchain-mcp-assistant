from typing import Optional
from urllib.parse import urlparse

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


_driver: Optional[webdriver.Chrome] = None


def _get_driver() -> webdriver.Chrome:
    global _driver

    if _driver is None:
        options = Options()

        # Keep browser visible for local demo.
        # Uncomment for headless mode:
        # options.add_argument("--headless=new")

        options.add_argument("--start-maximized")
        options.add_argument("--disable-notifications")

        _driver = webdriver.Chrome(options=options)

    return _driver


def _validate_url(url: str) -> str:
    parsed = urlparse(url)

    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Only http:// and https:// URLs are allowed.")

    return url


def _resolve_by(by: str):
    selectors = {
        "id": By.ID,
        "css": By.CSS_SELECTOR,
        "xpath": By.XPATH,
        "name": By.NAME,
        "class_name": By.CLASS_NAME,
        "tag_name": By.TAG_NAME,
        "link_text": By.LINK_TEXT,
        "partial_link_text": By.PARTIAL_LINK_TEXT,
    }

    key = by.lower().strip()

    if key not in selectors:
        raise ValueError(f"Unsupported selector type: {by}")

    return selectors[key]


def register_browser_tools(mcp):

    @mcp.tool()
    def browser_open_url(url: str) -> dict:
        """
        Open a website in the Selenium browser.
        """
        safe_url = _validate_url(url)

        driver = _get_driver()
        driver.get(safe_url)

        return {
            "status": "opened",
            "url": driver.current_url,
            "title": driver.title,
        }


    @mcp.tool()
    def browser_get_title() -> dict:
        """
        Get the current page title and URL.
        """
        driver = _get_driver()

        return {
            "title": driver.title,
            "url": driver.current_url,
        }


    @mcp.tool()
    def browser_get_page_text(max_chars: int = 4000) -> dict:
        """
        Read visible text from the current page.
        """
        driver = _get_driver()

        text = driver.find_element(By.TAG_NAME, "body").text

        return {
            "url": driver.current_url,
            "title": driver.title,
            "text": text[:max_chars],
        }


    @mcp.tool()
    def browser_click(
        by: str,
        value: str,
        timeout: int = 10,
    ) -> dict:
        """
        Click an element on the current page.

        Supported selector types:
        id, css, xpath, name, class_name,
        tag_name, link_text, partial_link_text.
        """
        driver = _get_driver()
        selector = _resolve_by(by)

        element = WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable((selector, value))
        )

        element.click()

        return {
            "status": "clicked",
            "selector_type": by,
            "selector": value,
            "url": driver.current_url,
        }


    @mcp.tool()
    def browser_type_text(
        by: str,
        value: str,
        text: str,
        clear_first: bool = True,
        timeout: int = 10,
    ) -> dict:
        """
        Type text into an input field on the current page.
        """
        driver = _get_driver()
        selector = _resolve_by(by)

        element = WebDriverWait(driver, timeout).until(
            EC.visibility_of_element_located((selector, value))
        )

        if clear_first:
            element.clear()

        element.send_keys(text)

        return {
            "status": "typed",
            "selector_type": by,
            "selector": value,
        }


    @mcp.tool()
    def browser_close() -> dict:
        """
        Close the Selenium browser session.
        """
        global _driver

        if _driver is None:
            return {"status": "already_closed"}

        _driver.quit()
        _driver = None

        return {"status": "closed"}
