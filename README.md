# 0 - NVidia transcription (NT)

Version **1.0.0** · Triggers **nvidia**, **NT** · Python 3.10+

Portable Agent Skill and command-line client for NVIDIA Riva hosted streaming speech recognition. Any agent with Markdown reading, Python execution and network access can use it. Agents without execution can provide the commands but cannot claim transcription occurred. Automatic skill discovery depends on the host; read `SKILL.md` directly if discovery is unavailable.

## Install

Download the release ZIP and extract the `0-nvidia-transcription-nt` folder into your agent's skills directory. It includes source, setup, documentation and tests. No model weights, GPU or local Riva server are required. NVIDIA account/API service access is required for real transcription and may incur charges or quota usage.

Windows PowerShell, from the extracted skill folder:

```powershell
python scripts/setup.py --env "$env:LOCALAPPDATA\nvidia-transcription-nt\venv"
& "$env:LOCALAPPDATA\nvidia-transcription-nt\venv\Scripts\python.exe" scripts/transcribe.py --check
& "$env:LOCALAPPDATA\nvidia-transcription-nt\venv\Scripts\python.exe" scripts/transcribe.py --input "C:\audio\speech.wav" --output "C:\audio\transcript.txt"
```

Linux/macOS:

```sh
python3 scripts/setup.py --env "$HOME/.local/share/nvidia-transcription-nt/venv"
"$HOME/.local/share/nvidia-transcription-nt/venv/bin/python" scripts/transcribe.py --input ./speech.wav --output ./transcript.txt
```

The CLI uses a hidden key prompt in an interactive terminal. For unattended agents, supply `NVIDIA_API_KEY` using the host's secret manager/environment. Do not embed keys in prompts, arguments, repositories or shared Drive. Python packages are downloaded from your configured pip index. Setup reuses an existing virtual environment and refuses a nonempty unrelated directory.

## Inputs and behavior

- Version 1 deliberately accepts only nonempty 16-bit mono PCM WAV. OGG/OPUS require explicit conversion using another installed tool; they are not implemented in this wrapper.
- Required: `--input`, `--output`. The output parent must exist; existing files are never overwritten.
- Optional: `--language` (default `en-US`), `--server` (default `grpc.nvcf.nvidia.com:443`), `--function-id` (default `71203149-d3b7-4460-8231-1be2543a1fca`), `--timeout` (positive seconds; default 300).
- Only final recognition alternatives are written as UTF-8 text. No timestamps, diarization, translation, language autodetection, microphone capture or local inference are provided by this release.
- The default function ID comes from the supplied parakeet-1_1b-rnnt-multilingual-asr instructions. Availability and language support must be checked against NVIDIA's current offering; a language option does not establish model support.
- TLS is enabled. Audio is streamed to the selected remote server. Output contains potentially private speech text.
- Exit codes: 0 = request completed (may recognize no speech); 2 = input/setup/local file error; 3 = gRPC failure. Argument parsing also uses code 2.
- No automatic retries. A timeout/failure can occur after the provider has processed some audio; investigate before rerunning. Partial transcripts are not saved on failed requests.

## Troubleshooting and validation

Run setup again for missing dependencies; `--check` verifies imports without API traffic. `python -m pip check` checks installed dependency consistency. An authentication/quota/service failure reports the gRPC status only, withholding raw provider details that might contain private data. Validate keys and account access privately. For unexpected local errors, inspect paths and environment without printing secrets.

Run `python -m unittest discover -s tests -v` using the installed environment. Tests use synthetic audio and a local fake service; they do **not** prove live NVIDIA acceptance, endpoint availability, credentials or transcription accuracy. Windows Python 3.14 was used for release checks; other platforms are supported by path handling but were not run natively.

## Files and provenance

`SKILL.md` is the portable contract; `agents/openai.yaml` is optional Codex UI metadata; `scripts/setup.py` installs the pinned `nvidia-riva-client==2.27.0`; `scripts/transcribe.py` implements transcription; `tests/` contains local checks. `VERSION`, `CHANGELOG.md` and `LICENSE` describe release identity and licensing.

Source: https://github.com/bahattab/nvidia-transcription-nt

Upstream API/client documentation: https://github.com/nvidia-riva/python-clients

Provider: https://build.nvidia.com/

This project contains an original wrapper, not a vendored copy of NVIDIA's repository. NVIDIA's dependencies retain their own licenses. No API keys, user audio or transcripts are distributed. A key previously exposed in chat must be replaced before operational use.
