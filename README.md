# Radiosonde Landed Waypoints GPX Generator

This project provides a Python script to extract the last seen and predicted landing coordinates of a radiosonde from a tracking website and generate a GPX waypoint file.

## Features

*   Fetches radiosonde data from `radiosondy.info`.
*   Parses the last seen and predicted landing coordinates.
*   Generates a GPX file with waypoints for both coordinates.
*   The GPX file is named with the sonde number and the last seen time (e.g., `403823_240912_1200_gpx_waypoint.gpx`).
*   Automatically sends the generated GPX file to a Telegram chat.

## Usage

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
    uv run python main.py http://www.radiosondy.info/sonde.php?t=2024091212_403823
    ```

    The script will generate a GPX file in the `gpx/` directory, named using the sonde number and the last seen time (e.g., `gpx/403823_240912_1200_gpx_waypoint.gpx`).

## Telegram Integration

This script can automatically send the generated GPX file to a Telegram chat. To enable this feature, you need to provide your Telegram bot token and chat ID.

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

    There are two ways to find your Telegram Chat ID:

    *   **Using a bot:** Send a message to your bot and then visit the following URL in your browser:

        ```
        https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates
        ```

        Replace `<YOUR_BOT_TOKEN>` with your bot's token. Look for the "chat" object in the JSON response; the "id" field is your chat ID.

    *   **Using the `find_chat_id.py` script:** This script uses the Telethon library to get the chat ID of any entity (user, channel, or group).

        a.  **Add your Telegram API credentials to the `.env` file:**

            ```
            API_ID=YOUR_API_ID
            API_HASH=YOUR_API_HASH
            ```

            You can get your `API_ID` and `API_HASH` from [my.telegram.org](https://my.telegram.org).

        b.  **Run the script:**

            ```bash
            uv run python find_chat_id.py <entity>
            ```

            Replace `<entity>` with the username or phone number of the entity (e.g., `'@mychannel'`, `'me'`).

4.  **Run the script:**

    When you run the `main.py` script, it will automatically detect the `.env` file, generate the GPX file, and send it to your specified Telegram chat.

## Contributing

Contributions are welcome! Please feel free to submit a pull request or open an issue.

## License

This project is licensed under the MIT License.
