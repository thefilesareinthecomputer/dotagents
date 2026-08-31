import unittest

from relay.errors import ToolFailed, ToolNotFound
from relay.llm.parsing import (ParseFailure, extract_json_block,
                               parse_tool_call)
from relay.tools.registry import get_registry
from relay.tools.web_tool import validate_url


class TestRegistry(unittest.TestCase):
    def test_known_tools_registered(self):
        names = get_registry().names()
        for expected in ("shell", "sql", "web", "read_file", "list_dir"):
            self.assertIn(expected, names)

    def test_unknown_tool_raises(self):
        with self.assertRaises(ToolNotFound):
            get_registry().dispatch("no-such-tool")


class TestWebValidation(unittest.TestCase):
    def test_metadata_host_refused(self):
        with self.assertRaises(ToolFailed):
            validate_url("http://169.254.169.254/latest/meta-data")

    def test_scheme_refused(self):
        with self.assertRaises(ToolFailed):
            validate_url("file:///etc/passwd")


class TestParsing(unittest.TestCase):
    def test_json_block(self):
        text = 'before\n```json\n{"a": 1}\n```\nafter'
        self.assertEqual(extract_json_block(text), {"a": 1})

    def test_json_failure_is_value(self):
        result = extract_json_block("no fences here")
        self.assertIsInstance(result, ParseFailure)

    def test_tool_call(self):
        call = parse_tool_call("CALL shell(command='ls -la', cwd=.)")
        self.assertEqual(call.tool, "shell")
        self.assertEqual(call.args["command"], "ls -la")


if __name__ == "__main__":
    unittest.main()
