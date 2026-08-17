# Gemini Project Context

## Project Overview
This is a Python script that takes a URL from a radiosonde tracking website, extracts the last seen and predicted landing coordinates, and generates a GPX waypoint file. The project uses `uv` for dependency management and the main script is `main.py`.

## Project Structure
- `main.py` - Main script that fetches radiosonde data from radiosondy.info, parses coordinates, generates GPX files, and sends them via Telegram
- `tests/test_main.py` - Unit tests covering all major functions
- `.github/workflows/ci.yml` - GitHub Actions CI workflow
- `.gemini/GEMINI.md` - This file
- `old/` - Legacy utility scripts (find_chat_id.py, update_version.py)

## Key Features
1. **Multi-format support**: Handles both `sonde.php` and `sonde_archive.php` page formats
2. **GPX generation**: Creates GPX files with 3 waypoints:
   - `{sonde} Last Seen` with `transport-airport` icon
   - `{sonde} My Predicted Landing` with `z-ico01` icon
   - `{sonde} radiosondy Landing Point` with `z-ico02` icon
3. **ZIP delivery**: Sends GPX files as ZIP archives via Telegram to prevent file corruption
4. **Auto-coordinate detection**: Extracts prediction coordinates from KML files automatically
5. **Locus compatibility**: Uses minimal GPX format (`<gpx version="1.1" creator="gpx.py">`)

## Dependencies
- beautifulsoup4 - HTML parsing
- python-dotenv - Environment variable management
- python-telegram-bot - Telegram integration
- requests - HTTP requests

## Testing
Run tests with: `PYTHONPATH=$PWD pytest tests/ -v`
Lint with: `ruff check .`
