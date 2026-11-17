# Radiosonde Landed Waypoints GPX Generator

This project provides a Python script to extract the last seen and predicted landing coordinates of a radiosonde from a tracking website and generate a GPX waypoint file.

## Features

*   Fetches radiosonde data from `radiosondy.info`.
*   Parses the last seen and predicted landing coordinates, including course and altitude.
*   Generates a GPX file with waypoints for both coordinates.
*   Adds the nearest city (e.g. `Rechtenbach (DE)`, without the distance) to every waypoint name and description.
*   The GPX file is named with the sonde number, the last seen time and the nearest city (e.g. `D23031952_261112_1109_Rechtenbach_DE_gpx_waypoint.gpx`).
*   Automatically sends the generated GPX file to a Telegram chat.

## Usage

**Important Note:** This script relies on the HTML structure of the `radiosondy.info` website. If the website's structure changes, the script may break.

1.  **Install Dependencies:**

    This project uses `uv` for package management. If you don't have it installed, you can install it with:

    ```bash
    pip install uv
    ```

    Then, install the project dependencies:

    ```bash
    uv sync
    ```

2.  **Run the Script:**

    Execute the `main.py` script with the URL of the radiosonde tracking page as an argument:

    ```bash
    uv run python main.py <URL>
    ```

    For example:

    ```bash
    uv run python main.py http://radiosondy.info/sonde_archive.php?sondenumber=W1150792
    ```

    The script will automatically scrape the balloon landing coordinates from the radiosondy.info website/map (via the map/GeoJSON data, with prediction KML as fallback) and generate a GPX file in the `gpx/` directory, named using the sonde number, the last seen time and the nearest city (e.g., `gpx/D23031952_261112_1109_Rechtenbach_DE_gpx_waypoint.gpx`).

## Hourly Tracker-Mail Automation

`check_tracker_mail.py` checks the Gmail inbox once an hour for new messages from
`tracker@radiosondy.info` and, for each one not handled before, runs `main.py` with the link from
the mail's **Details** button. `main.py` then generates the GPX file and sends it as a ZIP to
Telegram.

*   **Deduplication:** by the message `Message-ID`; a mail is handled at most once.
*   **Retry:** a mail whose script run fails is left unhandled, so the next hourly run retries it.
*   **State:** `~/.hermes/logs/radiosondy_mail_state.json` (handled message ids).
*   **Mailbox access:** IMAP read-only, same app password as the daily watch.
*   **Exit code:** `main.py` exits `0` only when the ZIP was actually delivered to Telegram,
  `1` otherwise — the handler relies on that and alerts on failure.
*   **Schedule:** hourly from the system crontab, `flock`-guarded:

    ```cron
    17 * * * * /usr/bin/flock -n /tmp/radiosondy_mail.lock /bin/bash -c 'cd /home/hermes/dev/radiosondy_landed_waypoints && .venv/bin/python check_tracker_mail.py' >> /home/hermes/.hermes/logs/radiosondy-mail.log 2>&1
    ```

Manual run (add `--dry-run` to skip running the GPX script):

```bash
.venv/bin/python check_tracker_mail.py
```

## Update Mail (new sonde, immediate)

`check_tracker_mail.py` runs hourly and is the **immediate** trigger: as soon as a new
`tracker@radiosondy.info` mail is in the inbox it

1. runs `main.py` with the link from the mail's "Details" button → GPX + Telegram ZIP, and
2. mails the sonde overview to `radiosonde@hornick.de`, subject `[Radiosondy] Neue Sonde <ID>`.

A message is processed at most once (`Message-ID`, remembered in
`~/.hermes/logs/radiosondy_mail_state.json`). A message whose GPX run fails is left unprocessed
so the next hourly run retries it. If the GPX succeeds but the mail fails, a ❌ goes to the
Hermes News Group.

## Daily Status-Change Watch (e-mail)

`check_status_changes.py` watches the radiosondes that `tracker@radiosondy.info` announces by
e-mail and reports new entries in a sonde's **Status Changes** section. It runs once a day and
stays silent when nothing changed.

*   **Source of sonde numbers:** every message from `tracker@radiosondy.info` in the Gmail inbox
    (`nick2faktor@gmail.com`), sonde number taken from the subject line.
*   **Trigger:** a table row that was not there on the previous run. Rows a sonde already had
    when it was first picked up are its baseline, not an update.
*   **Check:** the `Status Changes` table on `https://radiosondy.info/sonde_archive.php?sondenumber=<ID>`.
*   **Notification:** one e-mail per sonde to `radiosonde@hornick.de`, subject
    `[Radiosondy] <ID> Status Änderung: <STATUS>`, body contains the link, the sonde number and
    the new rows.
*   **Overview:** every notification also lists all watched sondes with their nearest city and
    predicted landing time, e.g. `D23029639 | Schönau (DE) | Landung: 2026-11-17 13:15 UTC`.
    Sondes without data yet show `-`.
*   **Links:** the mail is sent as plain text + HTML; in the HTML part the sonde number links to
    `https://radiosondy.info/sonde_archive.php?sondenumber=<ID>` (the plain text part carries the
    same URLs).
*   **Schedule:** daily at 11:35 (Europe/Berlin) from the system crontab, `flock`-guarded:

    ```cron
    35 11 * * * /usr/bin/flock -n /tmp/radiosondy_status.lock /bin/bash -c 'cd /home/hermes/dev/radiosondy_landed_waypoints && .venv/bin/python check_status_changes.py' >> /home/hermes/.hermes/logs/radiosondy-status.log 2>&1
    ```

*   **State:** `~/.hermes/logs/radiosondy_status_state.json` (already reported rows per sonde).
*   **Mailbox access:** IMAP read-only; the app password lives in
    `~/.hermes/secrets/gmail_app_password` and is never written to the config or the repo.
*   **Silent when nothing changes**; a run failure sends one ❌ to the Hermes News Group.

Manual run (add `--dry-run` to skip sending mail):

```bash
.venv/bin/python check_status_changes.py
```

## Telegram Integration

This script can automatically send the generated GPX file (zipped) to a Telegram chat. To enable this feature, you only need a Telegram bot token and chat ID.

1.  **Create a `.env` file:**

    Copy `.env.example` to `.env` in the root of the project directory. This file will hold your secret credentials.

2.  **Add your credentials to the `.env` file:**

    Open the `.env` file and add your bot token and chat ID in the following format:

    ```
    TELEGRAM_BOT_TOKEN=YOUR_BOT_TOKEN
    TELEGRAM_CHAT_ID=YOUR_CHAT_ID
    ```

    Replace `YOUR_BOT_TOKEN` and `YOUR_CHAT_ID` with your actual credentials. The `.env` file is included in the `.gitignore` file, so it will not be committed to your repository.

3.  **Create a bot and get the token:**

    Create a bot with [@BotFather](https://t.me/BotFather) using the `/newbot` command. BotFather will give you a token in the format `123456789:ABCDEF...`.

4.  **Get your Telegram Chat ID:**

    Send a message to your bot (you may need to start it with `/start`), then visit the following URL in your browser:

    ```
    https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates
    ```

    Replace `<YOUR_BOT_TOKEN>` with your bot's token. Look for the `"chat"` object in the JSON response; the `"id"` field is your chat ID. For groups/channels, the bot must be added to them and have permission to send messages/files.

5.  **Run the script:**

    When you run the `main.py` script, it will automatically detect the `.env` file, generate the GPX file, zip it, and send it to your specified Telegram chat.

## Contributing

Contributions are welcome! Please feel free to submit a pull request or open an issue.

## License

This project is licensed under the MIT License.

## Troubleshooting

### Windows Smart App Control / WDAC blocking package builds

If you see errors like:

```
error: Failed to build `pyaes==1.6.1`
  cause: Eine Anwendungssteuerungsrichtlinie hat diese Datei blockiert. (os error 4551)
```

Windows Smart App Control (or WDAC/App Control) may be blocking the build process. If the "On" toggle is grayed out in Windows Security, you can change it via the Registry.

#### Re-enable (set to On/Evaluation)

1. Press `Win + R`, type `regedit`, and hit `Enter` (run as Administrator).
2. Navigate to:
   ```text
   HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Control\CI\Policy
   ```
   (Or `ControlSet001` depending on your build)
3. Find the DWORD value `VerifiedAndReputablePolicyState`.
4. Double-click it and set the value:
   * `1` = On
   * `2` = Evaluation Mode
   * `0` = Off
5. Restart your PC.

#### Disable (if you need to build locally)

If you need to temporarily disable Smart App Control to build packages:

1. Open Registry Editor as Administrator (`regedit`).
2. Go to `HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Control\CI\Policy`.
3. Set `VerifiedAndReputablePolicyState` to `0` (Off).
4. Restart your PC.

**Note:** Disabling Smart App Control reduces system security. Only do this if necessary for local development and re-enable it when done.

## Releasing

This project uses an automated release workflow via GitHub Actions. To create a new release:

1.  **Ensure your changes are merged into the `main` branch.**

2.  **Create and push a new Git tag** with the desired version number (e.g., `v1.0.0`). The tag name should follow the `v*.*.*` pattern.
    ```bash
    git tag -a vX.Y.Z -m "Release vX.Y.Z"
    git push origin vX.Y.Z
    ```
    Replace `vX.Y.Z` with your actual version number (e.g., `v1.0.0`).

3.  **The GitHub Actions workflow will automatically:**
    *   Update the `version` in `pyproject.toml` to match the tag.
    *   Commit this version update back to the `main` branch.
    *   Create a GitHub Release associated with the tag, including release notes.

This automates the process of keeping `pyproject.toml` in sync with your release tags and creating formal GitHub Releases.

## Manual Test Execution

To run the project's tests manually:

1.  **Ensure `uv` is installed:**
    If you don't have `uv` installed, you can install it using `pip`:
    ```bash
    pip install uv
    ```

2.  **Create and activate a virtual environment:**
    It's best practice to run tests within a virtual environment to isolate dependencies.
    ```bash
    uv venv
    source .venv/bin/activate
    ```

3.  **Install project dependencies and test runners:**
    Install your project's dependencies, along with `ruff`, `pytest`, and `pytest-asyncio`:
    ```bash
    uv pip install -e . ruff pytest pytest-asyncio
    ```

4.  **Run the tests:**
    Navigate to your project's root directory and run `pytest`. The `PYTHONPATH=$PWD` ensures that Python can find your `main` module.
    ```bash
    PYTHONPATH=$PWD uv run pytest tests/
    ```
    Alternatively, if your virtual environment is activated, you can just run:
    ```bash
    pytest tests/
    ```