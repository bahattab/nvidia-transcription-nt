# Changelog

## 1.1.0 — 2026-10-27

- Added JSON word/segment timestamps in source-relative milliseconds, plus SRT and WebVTT caption export.
- Infer format from output extension or select it explicitly with `--format`; plain text remains compatible.
- Request NVIDIA word offsets only for timed output; fail without writing when offsets are missing, invalid or overlapping.
- Group captions using provider boundaries, eight-word/five-second targets and silence breaks. No generated timing or automatic retries.
- Added real-protobuf regression tests for multiple final results, interim filtering, units, missing timing and subtitle syntax. Live endpoint timing quality remains unverified.

## 1.0.0 — 2026-10-27

- Portable skill with the requested display name and nvidia/NT triggers.
- Isolated Python setup, pinned Riva client, TLS streaming ASR and UTF-8 transcripts.
- Hidden/environment credential input, WAV validation, deadlines and no automatic retries.
- Local functional tests and cross-agent instructions. Live NVIDIA acceptance remains unverified.
