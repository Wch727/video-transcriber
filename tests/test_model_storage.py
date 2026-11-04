import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import model_storage


class ModelStorageTests(unittest.TestCase):
    def test_all_engines_use_configured_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "config.json"
            config.write_text(json.dumps({"directory": str(root / "models")}), encoding="utf-8")
            with patch.object(model_storage, "CONFIG", config), patch.dict(os.environ, {"VIDEO_TEXT_MODEL_DIR": ""}):
                self.assertEqual(model_storage.model_directory("whisper"), root / "models" / "whisper")
                self.assertEqual(model_storage.model_directory("sensevoice"), root / "models" / "sensevoice")
                self.assertFalse((root / "models").exists())

    def test_environment_can_override_storage(self):
        with patch.dict(os.environ, {"VIDEO_TEXT_MODEL_DIR": "D:/ExampleModels"}):
            self.assertEqual(model_storage.model_root(), Path("D:/ExampleModels"))

    def test_bad_configuration_does_not_silently_download_to_c(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.json"
            config.write_text('{"directory": ""}', encoding="utf-8")
            with patch.object(model_storage, "CONFIG", config), patch.dict(os.environ, {"VIDEO_TEXT_MODEL_DIR": ""}):
                with self.assertRaises(ValueError):
                    model_storage.model_root()
