"""Transcribe mono PCM WAV through NVIDIA Riva; never persist API credentials."""
import argparse
import getpass
import os
from pathlib import Path
import sys
import wave

SERVER = 'grpc.nvcf.nvidia.com:443'
FUNCTION_ID = '71203149-d3b7-4460-8231-1be2543a1fca'

def validate_audio(path):
    with wave.open(str(path), 'rb') as audio:
        if audio.getnchannels() != 1 or audio.getsampwidth() != 2 or audio.getcomptype() != 'NONE':
            raise ValueError('Expected 16-bit mono PCM WAV')
        if audio.getnframes() == 0:
            raise ValueError('Audio file is empty')
        return audio.getframerate()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Check imports without sending audio')
    parser.add_argument('--input', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--language', default='en-US')
    parser.add_argument('--server', default=SERVER)
    parser.add_argument('--function-id', default=FUNCTION_ID)
    parser.add_argument('--timeout', type=float, default=300)
    a = parser.parse_args()
    import riva.client
    import grpc
    if a.check:
        from importlib.metadata import version
        print(f'CLIENT_CHECK_OK nvidia-riva-client={version("nvidia-riva-client")}')
        return 0
    if not a.input or not a.output:
        parser.error('--input and --output are required')
    if a.timeout <= 0:
        parser.error('--timeout must be positive')
    try:
        rate = validate_audio(a.input)
    except (OSError, ValueError, wave.Error, EOFError):
        print('Invalid input: provide a readable, nonempty 16-bit mono PCM WAV.', file=sys.stderr)
        return 2
    output = a.output.expanduser().resolve()
    if output.exists():
        print('Output already exists; choose a new path.', file=sys.stderr)
        return 2
    if not output.parent.is_dir():
        print('Output parent directory must exist.', file=sys.stderr)
        return 2
    key = os.environ.get('NVIDIA_API_KEY', '').strip()
    if not key and sys.stdin.isatty():
        key = getpass.getpass('NVIDIA API key: ').strip()
    if not key:
        print('Set NVIDIA_API_KEY privately or run with an interactive terminal.', file=sys.stderr)
        return 2
    auth = riva.client.Auth(uri=a.server, use_ssl=True, metadata_args=[
        ('function-id', a.function_id), ('authorization', f'Bearer {key}')])
    service = riva.client.ASRService(auth)
    config = riva.client.StreamingRecognitionConfig(config=riva.client.RecognitionConfig(
        encoding=riva.client.AudioEncoding.LINEAR_PCM, sample_rate_hertz=rate,
        language_code=a.language, max_alternatives=1, enable_automatic_punctuation=True),
        interim_results=False)
    pieces = []
    try:
        with riva.client.AudioChunkFileIterator(str(a.input), chunk_n_frames=1600) as chunks:
            from riva.client.asr import streaming_request_generator
            requests = streaming_request_generator(chunks, config)
            for response in service.stub.StreamingRecognize(
                    requests, metadata=auth.get_auth_metadata(), timeout=a.timeout):
                for result in response.results:
                    if result.is_final and result.alternatives:
                        pieces.append(result.alternatives[0].transcript)
    except grpc.RpcError as exc:
        print(f'NVIDIA request failed ({exc.code().name}); no automatic retry.', file=sys.stderr)
        return 3
    text = '\n'.join(pieces).strip()
    with output.open('x', encoding='utf-8') as stream:
        stream.write(text + ('\n' if text else ''))
    print(f'Transcript saved: {output}' if text else f'No speech recognized; empty transcript saved: {output}')
    return 0

if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ImportError, ValueError) as exc:
        print(f'Local setup or file operation failed ({type(exc).__name__}). Run setup/check and inspect paths.', file=sys.stderr)
        raise SystemExit(2)
