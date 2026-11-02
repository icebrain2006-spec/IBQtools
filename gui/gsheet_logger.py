import json
import logging
import threading
import urllib.request
import urllib.error
from typing import List, Any


def send_to_google_sheet_async(webhook_url: str, log_type: str, row_data: List[Any]) -> None:
    """
    Sends log data asynchronously to the Google Sheets Apps Script Webhook.
    Runs in a detached daemon thread to prevent UI blocking.
    """
    if not webhook_url or not webhook_url.startswith("http"):
        return

    def _worker():
        try:
            payload = json.dumps({
                "type": log_type,  # "work_log" or "cal_log"
                "row": row_data
            }).encode("utf-8")

            req = urllib.request.Request(
                webhook_url,
                data=payload,
                headers={
                    "Content-Type": "application/json; charset=utf-8",
                    "User-Agent": "IBQtools/2.1"
                },
                method="POST"
            )

            with urllib.request.urlopen(req, timeout=10) as resp:
                resp_text = resp.read().decode("utf-8", errors="replace")
                logging.getLogger("IBQtools").info(f"Google Sheet response: {resp_text}")
        except Exception as e:
            logging.getLogger("IBQtools").warning(f"Google Sheet upload failed: {e}")

    t = threading.Thread(target=_worker, daemon=True)
    t.start()


def test_google_sheet_connection(webhook_url: str) -> tuple[bool, str]:
    """
    Synchronously tests the Google Sheets webhook URL by sending a ping payload.
    """
    if not webhook_url or not webhook_url.startswith("http"):
        return False, "Invalid Webhook URL. It must start with http:// or https://"

    try:
        payload = json.dumps({
            "type": "test_ping",
            "row": ["PING_TEST", "IBQtools_Connection_Test", "SUCCESS"]
        }).encode("utf-8")

        req = urllib.request.Request(
            webhook_url,
            data=payload,
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "User-Agent": "IBQtools/2.1"
            },
            method="POST"
        )

        with urllib.request.urlopen(req, timeout=10) as resp:
            resp_body = resp.read().decode("utf-8", errors="replace")
            return True, f"Server responded successfully: {resp_body}"
    except urllib.error.HTTPError as e:
        return False, f"HTTP Error {e.code}: {e.reason}"
    except Exception as e:
        return False, f"Connection error: {e}"
