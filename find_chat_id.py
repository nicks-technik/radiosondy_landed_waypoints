import asyncio
import os
import argparse
from dotenv import load_dotenv
from telethon.sync import TelegramClient


async def main():
    """Main function to get the chat ID of a Telegram entity.

    This function parses command-line arguments for the entity, reads the
    Telegram API credentials from the .env file, and then uses the Telethon
    library to get and print the chat ID.
    """
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Get the Chat ID for a Telegram entity."
    )
    parser.add_argument(
        "entity",
        help="The username or phone number of the entity (e.g., '@mychannel', 'me').",
    )
    args = parser.parse_args()

    api_id = os.getenv("ENV_API_ID")
    api_hash = os.getenv("ENV_API_HASH")

    if not api_id or not api_hash:
        print("API_ID or API_HASH not found in .env file.")
        return

    async with TelegramClient("session_name", api_id, api_hash) as client:
        try:
            entity = await client.get_entity(args.entity)
            print(f"The Chat ID for '{args.entity}' is: {entity.id}")
        except ValueError:
            print(
                f"Could not find the entity '{args.entity}'. Please make sure the username is correct."
            )


if __name__ == "__main__":
    asyncio.run(main())