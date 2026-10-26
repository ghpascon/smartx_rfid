# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `LoggerManager` can log to a database (`database_url` or `database_manager`, optional `database_model`), alone or together with the file system. Rows are queued and inserted in batches via `DatabaseManager.bulk_insert` in a background thread, with bounded buffering, retry with backoff and poison-row isolation. New helpers: `flush()`, `wait_until_ready()`, `get_stats()`.
- `LoggerManager` defaults `base_filename` to the executed script name.

### Fixed

- `smartx_rfid.models.log.Logs` no longer subclasses `DeclarativeBase` directly (it failed on import) and has an isolated metadata.

### Changed

- Device `emit_event` now sends a `device` dict `{"name": ..., "serial_number": ...}` as the first `on_event` argument instead of the name string.
- `TagList.add`, `TagList.remove_tags_by_device`, `EventDispatcher.add/add_async` and `WebhookManager.post_event` accept a device dict (strings are converted to `{"name": name}`).
- Tags now include `device_serial_number`.
- Dispatch templates support `{serial_number}`, `{device}` and `{device[key]}`; examples updated.

## [9.0.0] - 2026-04-16

### Changed

- WebhookManager post -> post_events
- post can be custom

## [1.6.0] - 2026-01-16

### Added

- Add Xtrack support

## [1.5.0] - 2026-01-15

### Added

- Add webhook class

## [1.4.0] - 2026-01-15

### Added

- Add database class

## [1.3.0] - 2026-01-15

### Added

- Tid Parser

## [1.1.7] - 2026-01-14

### Added

- Clients
- Help functions

## [0.5.0] - 2026-01-13

### Added

- Add Tag List

## [0.4.0] - 2026-01-13

### Added

- Add R700 Device

## [0.3.0] - 2026-01-13

### Added

- Add X714 Device
- Add device types

## [0.2.0] - 2026-01-13

### Added

- Add TCP Device

## [0.1.0] - 2026-01-12

### Added

- Add Serial Device

## [0.0.0] - 2026-01-12

### Added

- Upload lib to pypl
- First commit to github
