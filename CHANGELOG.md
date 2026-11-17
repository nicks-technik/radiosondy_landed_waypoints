# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `check_status_changes.py`: daily watch of the "Status Changes" table on each tracked
  sonde's radiosondy.info archive page; new rows are mailed to `radiosonde@hornick.de`.
- Tracked sondes are taken from `tracker@radiosondy.info` messages in the Gmail inbox.
- Unit tests for subject parsing, table parsing and notification content.

## [1.1.0] - 2026-11-13

### Added
- Extraction of nearest city from radiosondy.info page.
- Inclusion of nearest city in GPX waypoint names and descriptions.
- Inclusion of nearest city slug in the generated GPX filename.

### Fixed
- Improved cleanup of temporary ZIP files during Telegram transmission.
