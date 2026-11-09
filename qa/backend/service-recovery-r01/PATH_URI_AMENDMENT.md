# CLI path identity correction

Root identified that concatenating a filesystem path into a SQLite URI or SQLAlchemy URL could reinterpret `?` and `#`. The CLI now uses `Path.as_uri()` for the read-only SQLite check and `URL.create` for the mutable isolated copy. No reconciliation policy changed.

The added CLI test uses a directory containing spaces, `?` and `#`; it verifies exact output mutations, unchanged input bytes, the output hash and absence of unexpected sibling files. The relevant suite passes **9 tests in 9.01 seconds**. Original validation receipt and logs remain unchanged; `path-uri-amendment-r02.json` binds revised code and test output. No live/runtime changes.
