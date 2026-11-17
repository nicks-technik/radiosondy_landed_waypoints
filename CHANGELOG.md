# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `check_tracker_mail.py`: hourly check for new `tracker@radiosondy.info` mail; runs `main.py`
  with the link from the mail's "Details" button so the GPX ZIP reaches Telegram.
- `check_status_changes.py`: daily watch of the "Status Changes" table on each tracked
  sonde's radiosondy.info archive page; new rows are mailed to `radiosonde@hornick.de`.
  Every notification also lists all watched sondes with nearest city and predicted landing time.
- The sonde archive page is fetched with a short retry so a transient failure does not
  silently produce an empty status list.
- The notification is now plain text + HTML, and every sonde in the list links to its
  radiosondy.info archive page.
- `radiosondy_web.py` (systemd user service `radiosondy-web.service`, port 12346): the count
  line in the mail links to a page that opens every watched sonde in its own tab.
- Tracked sondes are taken from `tracker@radiosondy.info` messages in the Gmail inbox.
- Unit tests for subject parsing, table parsing, notification and mail-link handling.

### Changed
- `main.py` now exits non-zero when no GPX was created or the Telegram delivery failed
  (previously it always exited 0), so the hourly handler can detect failures.

## [1.1.0] - 2026-11-13

### Added
- Extraction of nearest city from radiosondy.info page.
- Inclusion of nearest city in GPX waypoint names and descriptions.
- Inclusion of nearest city slug in the generated GPX filename.

### Fixed
- Improved cleanup of temporary ZIP files during Telegram transmission.
