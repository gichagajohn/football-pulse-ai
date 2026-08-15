"""
utils/http.py — Football Pulse AI
Shared HTTP session with exponential-backoff retry.
"""
import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from utils.logger import setup_logger
logger = setup_logger("http")
HEADERS = {
    "User-Agent": "FootballPulseAI/1.0 (automated football media bot)"
}
def make_session(
    retries: int = 3,
    backoff: float = 1.5,
    status_forcelist=(429, 500, 502, 503, 504)
) -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=retries,
        backoff_factor=backoff,
        status_forcelist=status_forcelist,
        allowed_methods=["GET", "POST"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update(HEADERS)
    return session
# Shared session (import this everywhere)
session = make_session()
def get_json(url: str, params: dict = None, headers: dict = None, timeout: int = 15):
    """GET → JSON with error handling. Returns dict or None."""
    try:
        resp = session.get(url, params=params, headers=headers, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else "?"
        body = None
        if e.response is not None:
            try:
                body = e.response.json()
            except ValueError:
                body = e.response.text[:500]
        logger.warning("HTTP %s for %s: %s", status, url, body)
    except requests.exceptions.RequestException as e:
        logger.warning("Request failed for %s: %s", url, e)
    except ValueError as e:
        logger.warning("JSON decode error for %s: %s", url, e)
    return None
def post_json(url: str, data: dict = None, headers: dict = None, files=None, timeout: int = 30):
    """POST → JSON. Returns (status_code, response_dict)."""
    try:
        if files:
            resp = session.post(url, data=data, files=files, headers=headers, timeout=timeout)
        else:
            resp = session.post(url, json=data, headers=headers, timeout=timeout)
        return resp.status_code, resp.json()
    except requests.exceptions.RequestException as e:
        logger.error("POST failed for %s: %s", url, e)
        return None, {"error": str(e)}
