"""Tests for the Valve KeyValues (VDF/ACF) parser."""

from __future__ import annotations

from pathlib import Path

import pytest

from tracker.discovery.kv_parser import KVParserError, parse_kv


FIXTURES = Path(__file__).parent / "fixtures"


class TestSimplePairs:
    """Parse simple key-value pairs."""

    def test_single_pair(self):
        data = '"key" "value"'
        assert parse_kv(data) == {"key": "value"}

    def test_multiple_pairs(self):
        data = '"a" "1"\n"b" "2"'
        assert parse_kv(data) == {"a": "1", "b": "2"}

    def test_values_with_spaces(self):
        data = '"game" "Counter-Strike 2"'
        assert parse_kv(data) == {"game": "Counter-Strike 2"}

    def test_empty_value(self):
        data = '"key" ""'
        assert parse_kv(data) == {"key": ""}

    def test_empty_input(self):
        assert parse_kv("") == {}

    def test_whitespace_only(self):
        assert parse_kv("   \n  \t  ") == {}


class TestNestedBlocks:
    """Parse nested { } blocks."""

    def test_single_nested_block(self):
        data = '"AppState"\n{\n"appid" "730"\n"name" "CS2"\n}'
        result = parse_kv(data)
        assert result == {"AppState": {"appid": "730", "name": "CS2"}}

    def test_deeply_nested_blocks(self):
        data = '"a"\n{\n"b"\n{\n"c" "d"\n}\n}'
        result = parse_kv(data)
        assert result == {"a": {"b": {"c": "d"}}}

    def test_multiple_nested_blocks(self):
        data = (
            '"Block1"\n{\n"x" "1"\n}\n'
            '"Block2"\n{\n"y" "2"\n}'
        )
        result = parse_kv(data)
        assert result == {"Block1": {"x": "1"}, "Block2": {"y": "2"}}

    def test_mixed_nested_and_flat_keys(self):
        data = '"top" "value"\n"Block"\n{\n"inner" "x"\n}'
        result = parse_kv(data)
        assert result == {"top": "value", "Block": {"inner": "x"}}

    def test_empty_block(self):
        data = '"Empty" {}'
        result = parse_kv(data)
        assert result == {"Empty": {}}


class TestComments:
    """Handle // comments."""

    def test_line_comment(self):
        data = '"key" "value" // this is a comment'
        assert parse_kv(data) == {"key": "value"}

    def test_comment_on_own_line(self):
        data = '// header comment\n"key" "value"'
        assert parse_kv(data) == {"key": "value"}

    def test_comment_after_block_close(self):
        data = '"a" { "b" "c" } // end comment'
        assert parse_kv(data) == {"a": {"b": "c"}}


class TestFullVDF:
    """Parse full Steam libraryfolders.vdf and appmanifest files."""

    def test_libraryfolders_vdf(self):
        text = (FIXTURES / "steam_libraryfolders.vdf").read_text("utf-8")
        result = parse_kv(text)
        assert "LibraryFolders" in result
        folders = result["LibraryFolders"]
        assert folders["1"] == "C:\\Program Files (x86)\\Steam"
        assert folders["2"] == "D:\\SteamLibrary"
        assert folders["3"] == "E:\\Games\\Steam"

    def test_appmanifest_730(self):
        text = (FIXTURES / "steam_appmanifest_730.acf").read_text("utf-8")
        result = parse_kv(text)
        assert "AppState" in result
        app = result["AppState"]
        assert app["appid"] == "730"
        assert app["name"] == "Counter-Strike 2"
        assert app["installdir"] == "Counter-Strike Global Offensive"
        assert "UserConfig" in app
        assert app["UserConfig"]["language"] == "english"

    def test_appmanifest_570(self):
        text = (FIXTURES / "steam_appmanifest_570.acf").read_text("utf-8")
        result = parse_kv(text)
        assert "AppState" in result
        app = result["AppState"]
        assert app["appid"] == "570"
        assert app["name"] == "Dota 2"


class TestMalformedInput:
    """Handle malformed input gracefully."""

    def test_unclosed_string(self):
        with pytest.raises(KVParserError):
            parse_kv('"key "value"')

    def test_unclosed_block(self):
        with pytest.raises(KVParserError):
            parse_kv('"a"\n{\n"b" "c"\n')

    def test_unexpected_close_brace(self):
        with pytest.raises(KVParserError):
            parse_kv('"a" "b"\n}')

    def test_junk_outside_quotes(self):
        with pytest.raises(KVParserError):
            parse_kv('"key" value_without_quotes')
