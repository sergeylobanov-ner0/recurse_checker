# External Uptime Monitor with Telegram Alerts

Simple Python script for external monitoring of web resources with Telegram notifications.

The script checks one or more websites from the outside, stores the last known state in JSON, writes logs to console and file, sends one alert when a resource becomes unavailable, and sends a separate recovery message when the resource becomes available again.

## What This Project Does

- Checks configured web resources every 15 minutes
- Uses HTTP GET with `requests`
- Treats HTTP `200-399` as `OK`
- Treats HTTP `400-599`, timeout, DNS error, connection error, SSL error, and other request exceptions as `PROBLEM`
- Sends Telegram alert on the first failed check
- Does not spam repeated alerts while the resource is still unavailable
- Sends a recovery message when the resource comes back
- Stores state between restarts in `monitor_state.json`
- Writes logs to console and `monitor.log`

## Project Files

- `recurse_checker.py` - main monitoring script
- `resources.json` - list of websites to monitor
- `monitor_state.json` - saved state between runs
- `monitor.log` - runtime logs

## Requirements

- Python 3
- `requests`

Install `requests` if needed:

```powershell
pip install requests
```

## Resource List

All monitored websites are stored in `resources.json`.

Current example:

```json
[
  {
    "name": "MOEX Main Page",
    "url": "https://www.moex.com/",
    "expected_status_min": 200,
    "expected_status_max": 399,
    "timeout": 10
  },
  {
    "name": "MOEX Passport",
    "url": "https://passport.moex.com/",
    "expected_status_min": 200,
    "expected_status_max": 399,
    "timeout": 10
  }
]
```

To add a new website, simply add one more JSON object to the list.

Example:

```json
{
  "name": "Python Homepage",
  "url": "https://www.python.org/",
  "expected_status_min": 200,
  "expected_status_max": 399,
  "timeout": 10
}
```

## Telegram Setup

The script uses Telegram Bot API and reads credentials from environment variables:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

PowerShell example:

```powershell
$env:TELEGRAM_BOT_TOKEN="your_bot_token"
$env:TELEGRAM_CHAT_ID="your_chat_id"
```

If these variables are missing, the script stops with a clear error message.

## How To Run

```powershell
python .\recurse_checker.py
```

If `python` is not available in your terminal:

```powershell
py .\recurse_checker.py
```

## Alert Format

```text
[ALERT] Resource unavailable
Name: <resource name>
URL: <url>
Time: <timestamp>
Status: <status code or EXCEPTION>
Details: <error text or short explanation>
```

## Recovery Format

```text
[RECOVERED] Resource is available again
Name: <resource name>
URL: <url>
Time: <timestamp>
Status: <status code>
Response time: <seconds>
```

## How State Works

The script stores the last known state of each resource in `monitor_state.json`.

This allows it to:

- remember whether the resource was already in `PROBLEM`
- avoid repeated alerts after restart
- send `RECOVERED` only when there is a real transition from `PROBLEM` to `OK`

## Logging

The script logs:

- check time
- resource name
- URL
- status code
- response time
- error text
- alert sending
- recovery sending

Logs are written to:

- console
- `monitor.log`

## Example Use Cases

- monitoring main company websites
- checking authentication portals
- tracking critical landing pages
- sending instant Telegram notifications to a private chat or group

## Tech Stack

- Python
- Standard Library
- `requests`
- Telegram Bot API

## Notes

- One Python file
- No async
- No database
- No Docker
- No third-party Telegram libraries
- Simple structure for easy manual editing
