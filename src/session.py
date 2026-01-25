"""
HTTP Session management for Epic MyChart.
Handles cookies, headers, and token persistence.
"""

import httpx
import random
import time
import logging
from typing import Optional

import config

logger = logging.getLogger(__name__)


class EpicSession:
    """Manages HTTP session state for Epic MyChart scheduling."""

    def __init__(self):
        self.client = httpx.Client(
            timeout=config.REQUEST_TIMEOUT,
            follow_redirects=True,
        )
        self._widget_header: Optional[str] = None
        self._setup_default_headers()

    def _setup_default_headers(self):
        """Set up default headers for all requests."""
        self.client.headers.update({
            "User-Agent": config.USER_AGENT,
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "X-Requested-With": "XMLHttpRequest",
            "api-key": config.API_KEY,
            "Origin": config.BASE_URL,
        })

    @property
    def widget_header(self) -> Optional[str]:
        """Get the current __widgetheader token."""
        return self._widget_header

    @widget_header.setter
    def widget_header(self, value: str):
        """Set the __widgetheader token."""
        self._widget_header = value
        logger.debug(f"Widget header updated: {value[:20]}...")

    def get_request_headers(self, referer: Optional[str] = None) -> dict:
        """Get headers for a request, including dynamic tokens."""
        headers = {}
        if self._widget_header:
            headers["__widgetheader"] = self._widget_header
        if referer:
            headers["Referer"] = referer
        return headers

    def post(
        self,
        endpoint: str,
        data: Optional[dict] = None,
        referer: Optional[str] = None,
        content_type: str = "application/x-www-form-urlencoded; charset=UTF-8",
    ) -> httpx.Response:
        """
        Make a POST request with proper headers and delay.

        Args:
            endpoint: The API endpoint (will be appended to BASE_URL)
            data: Form data to send
            referer: Optional referer header
            content_type: Content-Type header value

        Returns:
            httpx.Response object
        """
        # Add human-like delay
        delay = random.uniform(config.REQUEST_DELAY_MIN, config.REQUEST_DELAY_MAX)
        time.sleep(delay)

        url = f"{config.BASE_URL}{endpoint}"
        headers = self.get_request_headers(referer)
        headers["Content-Type"] = content_type

        logger.info(f"POST {endpoint}")
        logger.debug(f"Headers: {headers}")
        logger.debug(f"Data keys: {list(data.keys()) if data else 'None'}")

        response = self.client.post(url, data=data, headers=headers)

        logger.info(f"Response: {response.status_code}")
        logger.debug(f"Response cookies: {dict(response.cookies)}")

        return response

    def get(
        self,
        endpoint: str,
        params: Optional[dict] = None,
        referer: Optional[str] = None,
    ) -> httpx.Response:
        """
        Make a GET request with proper headers and delay.

        Args:
            endpoint: The API endpoint (will be appended to BASE_URL)
            params: Query parameters
            referer: Optional referer header

        Returns:
            httpx.Response object
        """
        delay = random.uniform(config.REQUEST_DELAY_MIN, config.REQUEST_DELAY_MAX)
        time.sleep(delay)

        url = f"{config.BASE_URL}{endpoint}"
        headers = self.get_request_headers(referer)

        logger.info(f"GET {endpoint}")

        response = self.client.get(url, params=params, headers=headers)

        logger.info(f"Response: {response.status_code}")

        return response

    def close(self):
        """Close the HTTP client."""
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
