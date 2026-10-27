"""Transcribe mono PCM WAV through NVIDIA Riva; never persist API credentials."""
import argparse
import getpass
import json
import math
import os
from pathlib import Path
import sys
import wave

SERVER = 'grpc.nvcf.nvidia.com:443'
FUNCTION_ID = '71203149-d3b7-4460-8231-1be2543a1fca'

class TimingError(ValueError):
    """The provider did not supply usable source-relative word offsets."""

def timed_segment(alternative, previous_end):
    words = []
    for info in alternative.words:
        start, end = int(info.start_time), int(info.end_time)
        if start < previous_end or end <= start or not info.word.strip():
            raise TimingError('Invalid or overlapping word offsets')
        words.append({'text': info.word, 'start_ms': start, 'end_ms': end})
        previous_end = end
    if not words:
        raise TimingError('No word offsets returned for recognized speech')
    return {'text': alternative.transcript, 'start_ms': words[0]['start_ms'],
            'end_ms': words[-1]['end_ms'], 'words': words}

def subtitle_cues(segments):
    """Group provider words without stretching or estimating their boundaries."""
    cues, group = [], []
    for segment in segments:
        for word in segment['words']:
            if group and (len(group) >= 8 or word['end_ms'] - group[0]['start_ms'] > 5000
                          or word['start_ms'] - group[-1]['end_ms'] >= 1000):
                cues.append(group)
                group = []
            group.append(word)
        if group:
            cues.append(group)
            group = []
    return cues

def timecode(ms, separator='.'):
    hours, remainder = divmod(ms, 3600000)
    minutes, remainder = divmod(remainder, 60000)
    seconds, millis = divmod(remainder, 1000)
    return f'{hours:02}:{minutes:02}:{seconds:02}{separator}{millis:03}'

def render_output(fmt, text, segments, language):
    if fmt == 'txt':
        return text + ('\n' if text else '')
    if fmt == 'json':
        return json.dumps({'schema_version': '1.0', 'time_unit': 'milliseconds',
                           'time_origin': 'input_audio_start', 'language': language,
                           'text': text, 'segments': segments}, ensure_ascii=False, indent=2) + '\n'
    blocks = []
    for index, words in enumerate(subtitle_cues(segments), 1):
        start, end = words[0]['start_ms'], words[-1]['end_ms']
        # Prevent recognized text from becoming subtitle markup or cue structure.
        caption = ' '.join(' '.join(w['text'].split()) for w in words)
        caption = caption.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        sep = ',' if fmt == 'srt' else '.'
        blocks.append(f'{index}\n{timecode(start, sep)} --> {timecode(end, sep)}\n{caption}\n')
    body = '\n'.join(blocks)
    return ('WEBVTT\n\n' if fmt == 'vtt' else '') + body

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
    parser.add_argument('--format', choices=['txt', 'json', 'srt', 'vtt'],
                        help='Default: infer from output suffix; otherwise plain text')
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
    if not math.isfinite(a.timeout) or a.timeout <= 0:
        parser.error('--timeout must be positive')
    fmt = a.format or (a.output.suffix.lower().lstrip('.') if a.output.suffix.lower() in
                       ('.txt', '.json', '.srt', '.vtt') else 'txt')
    timed = fmt != 'txt'
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
        language_code=a.language, max_alternatives=1, enable_automatic_punctuation=True,
        enable_word_time_offsets=timed),
        interim_results=False)
    pieces = []
    segments = []
    previous_end = 0
    try:
        with riva.client.AudioChunkFileIterator(str(a.input), chunk_n_frames=1600) as chunks:
            from riva.client.asr import streaming_request_generator
            requests = streaming_request_generator(chunks, config)
            for response in service.stub.StreamingRecognize(
                    requests, metadata=auth.get_auth_metadata(), timeout=a.timeout):
                for result in response.results:
                    if result.is_final and result.alternatives:
                        alternative = result.alternatives[0]
                        if not alternative.transcript.strip():
                            continue
                        pieces.append(alternative.transcript)
                        if timed:
                            segment = timed_segment(alternative, previous_end)
                            segments.append(segment)
                            previous_end = segment['end_ms']
    except TimingError:
        print('Timing export failed: NVIDIA returned missing, invalid or overlapping word offsets; '
              'no output saved and no retry. Confirm model word-timing support.', file=sys.stderr)
        return 4
    except grpc.RpcError as exc:
        print(f'NVIDIA request failed ({exc.code().name}); no automatic retry.', file=sys.stderr)
        return 3
    text = '\n'.join(pieces).strip()
    content = render_output(fmt, text, segments, a.language)
    with output.open('x', encoding='utf-8') as stream:
        stream.write(content)
    print(f'Transcript saved: {output}' if text else f'No speech recognized; output contains no speech: {output}')
    return 0

if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ImportError, ValueError) as exc:
        print(f'Local setup or file operation failed ({type(exc).__name__}). Run setup/check and inspect paths.', file=sys.stderr)
        raise SystemExit(2)
