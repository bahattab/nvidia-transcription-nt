import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch
import wave

spec = importlib.util.spec_from_file_location('nt', Path(__file__).resolve().parents[1] / 'scripts/transcribe.py')
nt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(nt)

class TranscriptionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.audio = self.root / 'input.wav'
        self.output = self.root / 'out.txt'
        self.wav()

    def wav(self, channels=1, width=2):
        with wave.open(str(self.audio), 'wb') as f:
            f.setnchannels(channels)
            f.setsampwidth(width)
            f.setframerate(16000)
            f.writeframes(b'\0' * (1600 * channels * width))

    def run_cli(self, service=None, extra=()):
        args = ['nt', '--input', str(self.audio), '--output', str(self.output), *extra]
        with patch('sys.argv', args), patch.dict(os.environ, {'NVIDIA_API_KEY': 'unit-test-only'}), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            if service is None:
                return nt.main()
            with patch('riva.client.ASRService', return_value=service):
                return nt.main()

    def test_wav_validation(self):
        self.assertEqual(nt.validate_audio(self.audio), 16000)
        self.wav(channels=2)
        with self.assertRaises(ValueError):
            nt.validate_audio(self.audio)

    def test_invalid_input_never_calls_service(self):
        self.wav(width=1)
        with patch('riva.client.ASRService') as service:
            self.assertEqual(self.run_cli(), 2)
            service.assert_not_called()

    def test_existing_output_untouched(self):
        self.output.write_text('original', encoding='utf-8')
        self.assertEqual(self.run_cli(), 2)
        self.assertEqual(self.output.read_text(), 'original')

    def test_streaming_request_and_utf8(self):
        def recognize(requests, metadata, timeout):
            items = list(requests)
            self.assertEqual(items[0].streaming_config.config.sample_rate_hertz, 16000)
            self.assertTrue(any(x.audio_content for x in items[1:]))
            self.assertEqual(timeout, 300)
            self.assertIn(('authorization', 'Bearer unit-test-only'), metadata)
            yield types.SimpleNamespace(results=[types.SimpleNamespace(is_final=True, alternatives=[types.SimpleNamespace(transcript='Hello مرحبا')])])
        service = types.SimpleNamespace(stub=types.SimpleNamespace(StreamingRecognize=recognize))
        self.assertEqual(self.run_cli(service), 0)
        self.assertEqual(self.output.read_text(encoding='utf-8'), 'Hello مرحبا\n')

    def test_rpc_failure_no_retry_or_output(self):
        import grpc
        calls = []
        class Denied(grpc.RpcError):
            def code(self):
                return grpc.StatusCode.UNAUTHENTICATED
        def recognize(*args, **kwargs):
            calls.append(1)
            raise Denied()
        service = types.SimpleNamespace(stub=types.SimpleNamespace(StreamingRecognize=recognize))
        self.assertEqual(self.run_cli(service), 3)
        self.assertEqual(len(calls), 1)
        self.assertFalse(self.output.exists())

    def timed_service(self, results, timing=True):
        from riva.client.proto import riva_asr_pb2 as pb
        def recognize(requests, metadata, timeout):
            config = next(iter(requests)).streaming_config.config
            self.assertEqual(config.enable_word_time_offsets, timing)
            for result in results:
                yield pb.StreamingRecognizeResponse(results=[result])
        return types.SimpleNamespace(stub=types.SimpleNamespace(StreamingRecognize=recognize))

    def result(self, text='Hello world.', words=None, final=True):
        from riva.client.proto import riva_asr_pb2 as pb
        if words is None:
            words = [('Hello', 1250, 1500), ('world.', 1600, 2100)]
        return pb.StreamingRecognitionResult(is_final=final, alternatives=[
            pb.SpeechRecognitionAlternative(transcript=text, words=[
                pb.WordInfo(word=w, start_time=s, end_time=e) for w, s, e in words])])

    def test_json_multiple_results_absolute_ms_and_interim_ignored(self):
        self.output = self.root / 'out.json'
        results = [self.result('interim', final=False), self.result(),
                   self.result('مرحبا', [('مرحبا', 5000, 5600)])]
        self.assertEqual(self.run_cli(self.timed_service(results)), 0)
        data = json.loads(self.output.read_text(encoding='utf-8'))
        self.assertEqual(data['time_unit'], 'milliseconds')
        self.assertEqual(data['time_origin'], 'input_audio_start')
        self.assertEqual(data['text'], 'Hello world.\nمرحبا')
        self.assertEqual(data['segments'][0]['words'][0]['start_ms'], 1250)
        self.assertEqual(data['segments'][1]['start_ms'], 5000)
        self.assertEqual(data['segments'][1]['end_ms'], 5600)

    def test_srt_and_vtt_exact_provider_boundaries(self):
        for fmt, delimiter, header in [('srt', ',', ''), ('vtt', '.', 'WEBVTT\n\n')]:
            with self.subTest(fmt=fmt):
                self.output = self.root / f'out.{fmt}'
                self.assertEqual(self.run_cli(self.timed_service([self.result()])), 0)
                self.assertEqual(self.output.read_text(encoding='utf-8'), header +
                    f'1\n00:00:01{delimiter}250 --> 00:00:02{delimiter}100\nHello world.\n')

    def test_missing_and_invalid_timings_fail_without_output(self):
        cases = [[], [('word', 10, 0)], [('word', -1, 10)],
                 [('one', 100, 300), ('two', 200, 400)]]
        for words in cases:
            with self.subTest(words=words):
                self.output = self.root / 'missing.json'
                self.assertEqual(self.run_cli(self.timed_service([self.result(words=words)])), 4)
                self.assertFalse(self.output.exists())

    def test_backward_offsets_across_results_fail(self):
        self.output = self.root / 'backward.srt'
        results = [self.result(), self.result('restart', [('restart', 100, 500)])]
        self.assertEqual(self.run_cli(self.timed_service(results)), 4)
        self.assertFalse(self.output.exists())

    def test_format_override_and_text_does_not_require_words(self):
        self.output = self.root / 'out.json'
        self.assertEqual(self.run_cli(self.timed_service([self.result(words=[])], timing=False),
                                     ['--format', 'txt']), 0)
        self.assertEqual(self.output.read_text(encoding='utf-8'), 'Hello world.\n')

    def test_no_speech_produces_valid_empty_timed_output(self):
        self.output = self.root / 'empty.json'
        self.assertEqual(self.run_cli(self.timed_service([])), 0)
        data = json.loads(self.output.read_text())
        self.assertEqual(data['segments'], [])
        self.assertEqual(data['text'], '')

    def test_cue_grouping_silence_limits_and_long_timecode(self):
        words = [(str(i), 3600000 + i * 400, 3600200 + i * 400) for i in range(10)]
        words.append(('after pause', 3610000, 3610500))
        segment = nt.timed_segment(self.result(words=words).alternatives[0], 0)
        cues = nt.subtitle_cues([segment])
        self.assertEqual([len(cue) for cue in cues], [8, 2, 1])
        self.assertEqual(nt.timecode(3661999, ','), '01:01:01,999')
        long_words = [('a', 0, 3000), ('b', 3000, 6000)]
        segment = nt.timed_segment(self.result(words=long_words).alternatives[0], 0)
        self.assertEqual(len(nt.subtitle_cues([segment])), 2)

    def test_caption_text_cannot_inject_markup_or_cues(self):
        segment = nt.timed_segment(self.result(words=[('<b>\n-->', 0, 100)]).alternatives[0], 0)
        rendered = nt.render_output('vtt', '', [segment], 'en-US')
        self.assertIn('&lt;b&gt; --&gt;', rendered)
        self.assertEqual(rendered.count('-->'), 1)

    def test_provider_point_timestamps_preserved_without_invented_duration(self):
        self.output = self.root / 'points.json'
        words = [('Hello', 0, 240), ('a', 880, 880), ('world', 1000, 1200)]
        self.assertEqual(self.run_cli(self.timed_service([self.result(words=words)])), 0)
        data = json.loads(self.output.read_text())
        self.assertEqual(data['segments'][0]['words'][1], {'text':'a', 'start_ms':880, 'end_ms':880})
        cues = nt.subtitle_cues(data['segments'])
        self.assertEqual(cues[0][-1]['end_ms'], 1200)

    def test_point_only_cue_merges_or_fails_without_guessing(self):
        a = nt.timed_segment(self.result(words=[('a',0,100)]).alternatives[0],0)
        b = nt.timed_segment(self.result(words=[('b',200,200)]).alternatives[0],100)
        self.assertEqual(len(nt.subtitle_cues([a,b])),1)
        self.assertEqual(nt.subtitle_cues([a,b])[0][-1]['end_ms'],200)
        with self.assertRaises(nt.TimingError):
            nt.subtitle_cues([b])

if __name__ == '__main__':
    unittest.main()
