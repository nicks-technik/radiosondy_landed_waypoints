# Radiosonde Landed Waypoints GPX Generator

This project provides a Python script to extract the last seen and predicted landing coordinates of a radiosonde from a tracking website and generate a GPX waypoint file. The project uses `uv` for dependency management and the main script is `main.py`.

## Features

* Fetches radiosonde data from `radiosondy.info`.
* Parses the last seen and predicted landing coordinates, including course and altitude.
* Generates a GPX file with three waypoints: **Last Seen**, **My Predicted Landing**, and **Radiosondy Landing Point** with distinct icons (`transport-airport`, `z-ico01`, `z-ico02`).
* The GPX file is named with the sonde number and the last seen time (e.g., `D20040532_260811_1152_gpx_waypoint.gpx`).
* Automatically sends the generated GPX file to a Telegram chat (zipped to prevent file corruption during transfer).
* Supports both `sonde.php` and `sonde_archive.php` page formats.

## Usage

**Important Note:** This script relies on the HTML structure of the `radiosondy.info` website. If the website's structure changes, the script may break.

### With `uv` (recommended)

1.  **Install `uv`:**
    ```bash
    pip install uv
    ```

2.  **Install Dependencies:**
    ```bash
    uv sync
    ```

3.  **Run the Script:**
    ```bash
    uv run python main.py <URL>
    ```

    For example:
    ```bash
    uv run python main.py https://radiosondy.info/sonde_archive.php?sondenumber=D20040532
    ```

    The script will generate a GPX file in the `gpx/` directory.

    You can also provide manual coordinates for a landing point using the `--coords` flag. The coordinates can be in one of two formats:
    *   `'lat,lon'` (e.g., `'50.22794,9.40322'`)
    *   `'lat,lon at YYYY-MM-DDTHH:MM:SS.ssZ'` (e.g., `'50.22794,9.40322 at 2025-09-12T13:05:49.25Z'`)

    When the second format is used, the date and time will be added as a description to the waypoint.

    Example with manual coordinates:
    ```bash
    uv run python main.py https://radiosondy.info/sonde_archive.php?sondenumber=D20040532 --coords '50.22794,9.40322 at 2025-09-12T13:05:49.25Z'
    ```

### With standard Python

1.  **Install Dependencies:**
    ```bash
    pip install beautifulsoup4 python-dotenv python-telegram-bot requests
    ```

2.  **Run the Script:**
    ```bash
    python main.py <URL>
    ```

## Telegram Integration

This script automatically sends the generated GPX file to a Telegram chat as a ZIP archive (to prevent file corruption during Telegram transfer). To enable this feature, you need to provide your Telegram bot token and chat ID.

1.  **Create a `.env` file:**
    Create a file named `.env` in the root of the project directory. This file will hold your secret credentials.

2.  **Add your credentials to the `.env` file:**
    Open the `.env` file and add your bot token and chat ID in the following format:

    ```
    TELEGRAM_BOT_TOKEN=YOUR_BOT_TOKEN
    TELEGRAM_CHAT_ID=YOUR_CHAT_ID
    ```

    Replace `YOUR_BOT_TOKEN` and `YOUR_CHAT_ID` with your actual credentials. The `.env` file is included in the `.gitignore` file, so it will not be committed to your repository.

3.  **Find your Telegram Chat ID:**
    *   **Using a bot:** Send a message to your bot and then visit the following URL in your browser:
        ```
        https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates
        ```
        Replace `<YOUR_BOT_TOKEN>` with your bot's token. Look for the "chat" object in the JSON response; the "id" field is your chat ID.
    *   **Using the `find_chat_id.py` script** (in the `old/` directory): This script uses the Telethon library to get the chat ID of any entity (user, channel, or group).

## Project Structure

```
radiosondy_landed_waypoints/
├── main.py                          # Main script for GPX generation
├── tests/
│   └── test_main.py                 # Unit tests
├── .gemini/
│   └── GEMINI.md                    # AI agent project context
├── .github/
│   └── workflows/
│       └── ci.yml                   # GitHub Actions CI workflow
├── old/
│   ├── find_chat_id.py              # Legacy Telethon utility
│   └── update_version.py            # Legacy version updater
├── .env                             # Environment secrets (not tracked)
└── .gitignore
```

## Testing

To run the project's tests manually:

1.  **Ensure dependencies are installed** (see above).

2.  **Run tests:**
    ```bash
    PYTHONPATH=$PWD pytest tests/ -v
    ```

    This will run all unit tests including coordinate parsing, landing point calculations, GPX generation, and KML parsing.

## Linting

This project uses `ruff` for linting:

```bash
ruff check .
```

## Contributing

Contributions are welcome! Please feel free to submit a pull request or open an issue.

## License

This project is licensed under the MIT License.

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
