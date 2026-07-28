"""Tests for config.json persistence."""

import json

import config

SETTINGS = {
    "line": [427, 0, 427, 480],
    "mode": "person",
    "flip_direction": False,
    "roi": None,
    "counts": {"in": 12, "out": 9},
}


class TestLoad:
    def test_missing_file_is_not_an_error(self, tmp_path):
        assert config.load(tmp_path / "nothing.json") == {}

    def test_reads_back_what_was_saved(self, tmp_path):
        path = tmp_path / "config.json"
        config.save(SETTINGS, path)
        assert config.load(path) == SETTINGS

    def test_corrupt_file_falls_back_to_defaults(self, tmp_path, capsys):
        # A half-written file after a power cut must not stop the counter.
        path = tmp_path / "config.json"
        path.write_text('{"line": [427, 0,')
        assert config.load(path) == {}
        assert "Failed to load config" in capsys.readouterr().out

    def test_a_json_list_is_rejected(self, tmp_path):
        # Valid JSON, wrong shape - callers expect a mapping.
        path = tmp_path / "config.json"
        path.write_text("[1, 2, 3]")
        assert config.load(path) == {}


class TestSave:
    def test_writes_readable_json(self, tmp_path):
        path = tmp_path / "config.json"
        config.save(SETTINGS, path)
        assert json.loads(path.read_text()) == SETTINGS

    def test_overwrites_rather_than_appends(self, tmp_path):
        path = tmp_path / "config.json"
        config.save({"mode": "person"}, path)
        config.save({"mode": "vehicle"}, path)
        assert config.load(path) == {"mode": "vehicle"}

    def test_an_unwritable_path_warns_instead_of_raising(self, tmp_path, capsys):
        # A read-only filesystem should not take down a working counter.
        config.save(SETTINGS, tmp_path / "no-such-dir" / "config.json")
        assert "Failed to save config" in capsys.readouterr().out
