"""S02: ArgSubstitutor"""
from sensenova_claw.capabilities.skills.arg_substitutor import substitute_arguments, parse_arguments


class TestArgSubstitutor:
    def test_parse_simple(self):
        assert parse_arguments("a b c") == ["a", "b", "c"]

    def test_parse_quoted(self):
        assert parse_arguments('a "b c" d') == ["a", "b c", "d"]

    def test_parse_empty(self):
        assert parse_arguments("") == []

    def test_substitute_all(self):
        result = substitute_arguments("Do: $ARGUMENTS", "hello world")
        assert "hello world" in result

    def test_substitute_indexed(self):
        result = substitute_arguments("$ARGUMENTS[0] and $ARGUMENTS[1]", "foo bar")
        assert "foo" in result and "bar" in result

    def test_substitute_shorthand(self):
        result = substitute_arguments("first=$0 second=$1", "a b")
        assert "first=a" in result
        assert "second=b" in result

    def test_substitute_no_placeholder(self):
        """无占位符时追加 ARGUMENTS"""
        result = substitute_arguments("plain body", "arg1 arg2")
        assert "ARGUMENTS: arg1 arg2" in result

    def test_substitute_no_args(self):
        """无参数时不追加"""
        result = substitute_arguments("plain body", "")
        assert "ARGUMENTS:" not in result

    def test_indexed_out_of_range(self):
        """索引越界返回空串"""
        result = substitute_arguments("$ARGUMENTS[5]", "a b")
        assert result.strip() == ""
