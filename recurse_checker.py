"""External web resource monitor with Telegram notifications.

The script checks configured web resources in a loop, stores state in JSON,
and sends Telegram alerts when a resource becomes unavailable or recovers.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import requests


CHECK_INTERVAL_SECONDS = 900
REQUEST_TIMEOUT = 10
STATE_FILE = "monitor_state.json"
LOG_FILE = "monitor.log"
RESOURCES_FILE = "resources.json"
USER_AGENT = "External-Uptime-Monitor/1.0"


@dataclass
class CheckResult:
    """Result of a single resource check."""

    resource_name: str
    url: str
    success: bool
    status_code: Optional[int]
    response_time: Optional[float]
    error: Optional[str]
    checked_at: str


def setup_logging() -> None:
    """Configure logging to console and file."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
        ],
    )


def load_state() -> Dict[str, Dict[str, Any]]:
    """Load monitor state from JSON file."""
    state_path = Path(STATE_FILE)
    if not state_path.exists():
        return {}

    try:
        with state_path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (json.JSONDecodeError, OSError) as error:
        logging.warning("Could not load state file %s: %s", STATE_FILE, error)
        return {}

    if isinstance(data, dict):
        return data

    logging.warning("State file %s has invalid format. Starting with empty state.", STATE_FILE)
    return {}


def save_state(state: Dict[str, Dict[str, Any]]) -> None:
    """Save monitor state to JSON file."""
    try:
        with Path(STATE_FILE).open("w", encoding="utf-8") as file:
            json.dump(state, file, ensure_ascii=False, indent=2)
    except OSError as error:
        logging.exception("Could not save state file %s: %s", STATE_FILE, error)


def send_telegram_message(text: str) -> None:
    """Send a plain text message to Telegram via Bot API."""
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not bot_token:
        raise RuntimeError("Environment variable TELEGRAM_BOT_TOKEN is not set.")
    if not chat_id:
        raise RuntimeError("Environment variable TELEGRAM_CHAT_ID is not set.")

    api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
    }

    response = requests.post(api_url, json=payload, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()

    telegram_result = response.json()
    if not telegram_result.get("ok"):
        description = telegram_result.get("description", "Unknown Telegram API error")
        raise RuntimeError(f"Telegram API returned an error: {description}")


def load_resources() -> list[Dict[str, Any]]:
    """Load resources to monitor from JSON file."""
    resources_path = Path(RESOURCES_FILE)
    if not resources_path.exists():
        raise RuntimeError(
            f"Resources file {RESOURCES_FILE} was not found. "
            "Create it next to the script and add at least one resource."
        )

    try:
        with resources_path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (json.JSONDecodeError, OSError) as error:
        raise RuntimeError(f"Could not load resources file {RESOURCES_FILE}: {error}") from error

    if not isinstance(data, list) or not data:
        raise RuntimeError(
            f"Resources file {RESOURCES_FILE} must contain a non-empty JSON list."
        )

    required_fields = {"name", "url"}
    for index, resource in enumerate(data, start=1):
        if not isinstance(resource, dict):
            raise RuntimeError(
                f"Resource #{index} in {RESOURCES_FILE} must be a JSON object."
            )

        missing_fields = required_fields - resource.keys()
        if missing_fields:
            missing_text = ", ".join(sorted(missing_fields))
            raise RuntimeError(
                f"Resource #{index} in {RESOURCES_FILE} is missing required fields: {missing_text}"
            )

        resource.setdefault("expected_status_min", 200)
        resource.setdefault("expected_status_max", 399)
        resource.setdefault("timeout", REQUEST_TIMEOUT)

    return data


def check_resource(resource: Dict[str, Any]) -> CheckResult:
    """Check one resource using HTTP GET and return the result."""
    name = resource["name"]
    url = resource["url"]
    timeout = resource.get("timeout", REQUEST_TIMEOUT)
    expected_status_min = resource.get("expected_status_min", 200)
    expected_status_max = resource.get("expected_status_max", 399)
    checked_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

    headers = {
        "User-Agent": USER_AGENT,
    }

    try:
        start_time = time.perf_counter()
        response = requests.get(
            url,
            headers=headers,
            timeout=timeout,
            allow_redirects=True,
            verify=True,
        )
        response_time = round(time.perf_counter() - start_time, 3)
        success = expected_status_min <= response.status_code <= expected_status_max

        return CheckResult(
            resource_name=name,
            url=url,
            success=success,
            status_code=response.status_code,
            response_time=response_time,
            error=None if success else f"Unexpected status code: {response.status_code}",
            checked_at=checked_at,
        )
    except requests.exceptions.RequestException as error:
        return CheckResult(
            resource_name=name,
            url=url,
            success=False,
            status_code=None,
            response_time=None,
            error=str(error),
            checked_at=checked_at,
        )


def format_alert_message(result: CheckResult) -> str:
    """Build Telegram alert text for a failed check."""
    status_text = str(result.status_code) if result.status_code is not None else "EXCEPTION"
    details = result.error or "No additional details"

    return (
        "[ALERT] Resource unavailable\n"
        f"Name: {result.resource_name}\n"
        f"URL: {result.url}\n"
        f"Time: {result.checked_at}\n"
        f"Status: {status_text}\n"
        f"Details: {details}"
    )


def format_recovered_message(result: CheckResult) -> str:
    """Build Telegram message for a recovered resource."""
    response_time_text = (
        f"{result.response_time:.3f} sec" if result.response_time is not None else "N/A"
    )

    return (
        "[RECOVERED] Resource is available again\n"
        f"Name: {result.resource_name}\n"
        f"URL: {result.url}\n"
        f"Time: {result.checked_at}\n"
        f"Status: {result.status_code}\n"
        f"Response time: {response_time_text}"
    )


def parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    """Parse ISO datetime from state file."""
    if not value:
        return None

    try:
        return datetime.fromisoformat(value)
    except ValueError:
        logging.warning("Could not parse datetime value from state: %s", value)
        return None


def process_result(
    resource: Dict[str, Any],
    result: CheckResult,
    state: Dict[str, Dict[str, Any]],
) -> None:
    """Update state and send Telegram notifications on state transitions."""
    resource_key = resource["name"]
    previous_state = state.get(
        resource_key,
        {
            "current_state": "OK",
            "last_status_code": None,
            "last_error": None,
            "last_check_time": None,
            "alert_sent": False,
            "problem_started_at": None,
            "last_alert_time": None,
        },
    )

    current_state = "OK" if result.success else "PROBLEM"
    current_check_time = parse_iso_datetime(result.checked_at)
    last_alert_time = parse_iso_datetime(previous_state.get("last_alert_time"))

    logging.info(
        "Checked resource | name=%s | url=%s | status_code=%s | response_time=%s | error=%s",
        result.resource_name,
        result.url,
        result.status_code,
        result.response_time,
        result.error,
    )

    should_repeat_alert = (
        current_state == "PROBLEM"
        and previous_state.get("current_state") == "PROBLEM"
        and last_alert_time is not None
        and current_check_time is not None
        and current_check_time - last_alert_time >= timedelta(seconds=CHECK_INTERVAL_SECONDS)
    )

    if current_state == "PROBLEM" and (
        not previous_state.get("alert_sent", False) or should_repeat_alert
    ):
        message = format_alert_message(result)
        send_telegram_message(message)
        logging.warning("Alert sent for resource: %s", result.resource_name)
        alert_sent = True
        problem_started_at = previous_state.get("problem_started_at") or result.checked_at
        last_alert_time_value = result.checked_at
    elif current_state == "OK" and previous_state.get("current_state") == "PROBLEM":
        message = format_recovered_message(result)
        send_telegram_message(message)
        logging.info("Recovered message sent for resource: %s", result.resource_name)
        alert_sent = False
        problem_started_at = None
        last_alert_time_value = None
    else:
        alert_sent = current_state == "PROBLEM" and previous_state.get("alert_sent", False)
        problem_started_at = (
            previous_state.get("problem_started_at") if current_state == "PROBLEM" else None
        )
        last_alert_time_value = (
            previous_state.get("last_alert_time") if current_state == "PROBLEM" else None
        )

        if current_state == "PROBLEM" and not problem_started_at:
            problem_started_at = result.checked_at

    state[resource_key] = {
        "current_state": current_state,
        "last_status_code": result.status_code,
        "last_error": result.error,
        "last_check_time": result.checked_at,
        "alert_sent": alert_sent,
        "problem_started_at": problem_started_at,
        "last_alert_time": last_alert_time_value,
    }


def validate_environment() -> None:
    """Ensure required Telegram environment variables are present."""
    if not os.getenv("TELEGRAM_BOT_TOKEN"):
        raise RuntimeError("Environment variable TELEGRAM_BOT_TOKEN is not set.")
    if not os.getenv("TELEGRAM_CHAT_ID"):
        raise RuntimeError("Environment variable TELEGRAM_CHAT_ID is not set.")


def main() -> None:
    """Run the monitoring loop forever."""
    setup_logging()
    validate_environment()
    resources = load_resources()
    state = load_state()

    logging.info("Started external resource monitor. Check interval: %s seconds", CHECK_INTERVAL_SECONDS)

    while True:
        for resource in resources:
            try:
                result = check_resource(resource)
                process_result(resource, result, state)
            except Exception as error:  # noqa: BLE001
                resource_name = resource.get("name", "Unknown resource")
                logging.exception("Unhandled error while processing resource %s: %s", resource_name, error)
            finally:
                save_state(state)

        logging.info("Sleeping for %s seconds before next check cycle", CHECK_INTERVAL_SECONDS)
        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
