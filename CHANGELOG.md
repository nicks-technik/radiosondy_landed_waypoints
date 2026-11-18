# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `check_tracker_mail.py`: hourly check for new `tracker@radiosondy.info` mail; runs `main.py`
  with the link from the mail's "Details" button so the GPX ZIP reaches Telegram, and mails the
  sonde overview to `radiosonde@hornick.de` (`[Radiosondy] Neue Sonde <ID>`).
- `check_status_changes.py`: daily watch of the "Status Changes" table on each tracked
  sonde's radiosondy.info archive page; new rows are mailed to `radiosonde@hornick.de`.
  Every notification also lists all watched sondes with nearest city, predicted landing time,
  the "Entfernung von Deinem QTH" and the receiver taken from the tracker mail, sorted
  youngest first. The watched set is exactly the tracker mails in the inbox — a deleted mail
  drops the sonde.
- `check_tracker_mail.py` processes a sonde at most once: if `nickl` and `nicklmhf` both get a
  mail for the same sonde, only one GPX run and one Telegram ZIP happen. `--dry-run` no longer
  writes the state file.
- Fixed the status baseline: rows a sonde already had when it was first picked up are now saved
  as the baseline, so the next run does not report them as changes.
- The sonde archive page is fetched with a short retry so a transient failure does not
  silently produce an empty status list.
- The notification is now plain text + HTML, and every sonde in the list links to its
  radiosondy.info archive page.
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
