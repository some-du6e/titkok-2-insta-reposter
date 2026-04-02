from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.components import queue_store
from src.components.pipeline import QueueValidationError, update_queue_settings


class QueueStoreSettingsTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.original_queue_path = queue_store.QUEUE_PATH
        queue_store.QUEUE_PATH = Path(self.temp_dir.name) / "queue.json"
        self.addCleanup(self._restore_queue_path)

    def _restore_queue_path(self):
        queue_store.QUEUE_PATH = self.original_queue_path

    def test_normalize_settings_defaults_cover_intro_to_disabled(self):
        settings = queue_store.normalize_settings(None, persist_existing_schedule=False)

        self.assertFalse(settings["prependCoverIntroEnabled"])

    def test_update_queue_settings_rejects_non_boolean_cover_intro_flag(self):
        with self.assertRaises(QueueValidationError):
            update_queue_settings({"prependCoverIntroEnabled": "yes"})


if __name__ == "__main__":
    unittest.main()
