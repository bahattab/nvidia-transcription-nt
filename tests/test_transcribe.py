import contextlib
import importlib.util
import io
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

    def run_cli(self, service=None):
        args = ['nt', '--input', str(self.audio), '--output', str(self.output)]
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

if __name__ == '__main__':
    unittest.main()
