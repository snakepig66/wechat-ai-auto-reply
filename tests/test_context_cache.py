"""Tests for the persistent per-contact context archive."""

import os
import sys
import shutil
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.context_cache import ContextCache


class ContextCacheTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp(prefix="context_cache_test_")
        self.addCleanup(shutil.rmtree, self._tmpdir, ignore_errors=True)
        self.path = os.path.join(self._tmpdir, "context_cache.json")

    def test_merge_dedupes_and_caps(self):
        cache = ContextCache(self.path, max_messages=3, save_every=1)
        cache.merge("a", [
            {"role": "user", "content": "1"},
            {"role": "user", "content": "2"},
        ])
        cache.merge("a", [
            {"role": "user", "content": "2"},
            {"role": "user", "content": "3"},
            {"role": "user", "content": "4"},
        ])
        assert [m["content"] for m in cache.get("a")] == ["2", "3", "4"]
        reloaded = ContextCache(self.path, max_messages=3)
        assert [m["content"] for m in reloaded.get("a")] == [
            "2", "3", "4"
        ]

    def test_in_memory_mode(self):
        cache = ContextCache(None)
        cache.append("a", "assistant", "hi")
        assert cache.get("a") == [{"role": "assistant", "content": "hi"}]
        cache.save()  # no-op without a path


if __name__ == "__main__":
    unittest.main()
