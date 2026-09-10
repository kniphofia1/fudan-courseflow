import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.transcriber import Transcriber


class TranscriberLanguageTests(unittest.TestCase):
    def test_language_is_passed_to_recognizer(self):
        for language in ("zh", "auto"):
            with self.subTest(language=language), \
                 patch("src.transcriber.config.SENSEVOICE_LANGUAGE", language), \
                 patch("src.transcriber.os.path.isfile", return_value=True), \
                 patch("src.transcriber.sherpa_onnx.OfflineRecognizer.from_sense_voice") as factory, \
                 patch("src.transcriber.sherpa_onnx.VadModelConfig"), \
                 patch("src.transcriber.sherpa_onnx.VoiceActivityDetector"):
                transcriber = Transcriber()
                transcriber._init()
                self.assertEqual(factory.call_args.kwargs["language"], language)
                transcriber._init()
                factory.assert_called_once()

    def test_mixed_chinese_english_output_is_not_filtered(self):
        transcriber = Transcriber()
        transcriber._vad = MagicMock()
        transcriber._vad.empty.side_effect = [False, True]
        transcriber._recognizer = MagicMock()
        stream = transcriber._recognizer.create_stream.return_value
        stream.result = SimpleNamespace(text="  注意 Transformer 的 attention mechanism。  ")
        texts = []
        transcriber._drain_segments(texts)
        self.assertEqual(texts, ["注意 Transformer 的 attention mechanism。"])
