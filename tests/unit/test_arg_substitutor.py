"""$ARGUMENTS 参数替换逻辑单测"""
import pytest
from sensenova_claw.capabilities.skills.arg_substitutor import substitute_arguments, parse_arguments


class TestParseArguments:
    def test_simple_split(self):
        assert parse_arguments("foo bar baz") == ["foo", "bar", "baz"]

    def test_quoted_string(self):
        assert parse_arguments('foo "bar baz" qux') == ["foo", "bar baz", "qux"]

    def test_single_quoted(self):
        assert parse_arguments("foo 'bar baz' qux") == ["foo", "bar baz", "qux"]

    def test_empty(self):
        assert parse_arguments("") == []

    def test_whitespace_only(self):
        assert parse_arguments("   ") == []


class TestSubstituteArguments:
    def test_arguments_placeholder(self):
        body = "Process $ARGUMENTS now"
        result = substitute_arguments(body, "file.pdf --verbose")
        assert result == "Process file.pdf --verbose now"

    def test_indexed_placeholder(self):
        body = "Convert $ARGUMENTS[0] to $ARGUMENTS[1]"
        result = substitute_arguments(body, "input.pdf markdown")
        assert result == "Convert input.pdf to markdown"

    def test_shorthand_placeholder(self):
        body = "Convert $0 to $1"
        result = substitute_arguments(body, "input.pdf markdown")
        assert result == "Convert input.pdf to markdown"

    def test_no_placeholder_appends(self):
        body = "Do the task"
        result = substitute_arguments(body, "extra args")
        assert result == "Do the task\n\nARGUMENTS: extra args"

    def test_empty_arguments(self):
        body = "Do $ARGUMENTS"
        result = substitute_arguments(body, "")
        assert result == "Do "

    def test_mixed_placeholders(self):
        body = "All: $ARGUMENTS, first: $0, second: $ARGUMENTS[1]"
        result = substitute_arguments(body, 'a "b c"')
        assert result == 'All: a "b c", first: a, second: b c'
