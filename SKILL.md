---
name: 0-nvidia-transcription-nt
description: 'Transcribe local speech audio using NVIDIA Riva hosted gRPC ASR. Display name: 0 - NVidia transcription (NT). Trigger on nvidia or standalone NT when invoking this skill or requesting speech transcription; do not route unrelated NVIDIA hardware questions here.'
metadata:
  version: 1.0.0
---

# 0 - NVidia transcription (NT)

Triggers: `nvidia`, `NT` (case insensitive).

Use NVIDIA hosted Riva speech recognition to produce UTF-8 text from a local audio file. This skill is portable: any agent can read this file and run the Python scripts with a shell. No Codex, Claude, MCP, Git, or Drive integration is required at runtime.

## Setup

Resolve this skill directory from the file you loaded. Run:

```text
python scripts/setup.py --env <writable-private-environment-directory>
<environment-python> scripts/transcribe.py --check
```

Use the environment's `Scripts/python.exe` on Windows or `bin/python` on Linux/macOS. Python 3.10+ and internet access are required. Keep the environment outside shared skills and source control. Setup installs the pinned client dependency and verifies imports and dependency consistency. Read [README.md](README.md) for platform commands, configuration, limitations and troubleshooting.

## Transcribe

1. Resolve the user's actual audio file and desired output path. Check that sending it to NVIDIA is within their request; explain remote processing if it is not already clear. Do not upload unrelated files.
2. Obtain `NVIDIA_API_KEY` from the host's private secret environment, or let an interactive human enter it through the hidden prompt. Never ask for a key in chat, store it in the package, print it, or put it in command arguments.
3. Run the environment Python:

```text
<environment-python> scripts/transcribe.py --input <audio.wav> --output <transcript.txt>
```

4. Require exit code zero and an actual output file. Report empty recognition as empty, not as a successful speech transcript. Summarization and translation are separate downstream steps; preserve the original transcript.

Defaults: TLS `grpc.nvcf.nvidia.com:443`, function ID `71203149-d3b7-4460-8231-1be2543a1fca`, language `en-US`. Set `--language` for a supported language; do not infer universal multilingual or Arabic support. Endpoint/function availability is controlled by NVIDIA; the scripts allow explicit overrides. This is a client installation, not a local model/server installation.

Version 1 supports PCM WAV, 16-bit, mono. Reject other formats before a network call. If conversion is requested, use an installed audio converter to create a separate WAV and verify it; retain the original. Do not silently rename compressed audio.

No automatic API retries: stop on authentication, quota, timeout or service error, report a sanitized failure and resolve the cause before another paid request. Never claim live service acceptance from an import check. Transcript files can contain private content; save only to the requested destination.
