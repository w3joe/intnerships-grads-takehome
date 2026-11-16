"""Exercise the executable as a user would, including its output streams."""

import json
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class CliTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.schedule = self.directory / "schedule.json"
        self.overrides = self.directory / "overrides.json"
        self.schedule.write_bytes((ROOT / "examples/schedule.json").read_bytes())
        self.overrides.write_bytes((ROOT / "examples/overrides.json").read_bytes())

    def run_cli(self, *arguments):
        return subprocess.run(
            [str(ROOT / "render-schedule"), *arguments],
            cwd=self.directory,
            capture_output=True,
            text=True,
            timeout=10,
        )

    def render(self, *arguments):
        return self.run_cli(
            f"--schedule={self.schedule}",
            f"--overrides={self.overrides}",
            "--from=2026-11-06T17:00:00Z",
            "--until=2026-11-20T17:00:00Z",
            *arguments,
        )

    def assert_cli_error(self, result, message):
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn(message, result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_documented_example_from_another_directory(self):
        result = self.render()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        expected = json.loads((ROOT / "examples/expected.json").read_text(encoding="utf-8"))
        self.assertEqual(json.loads(result.stdout), expected)

    def test_separate_argument_values(self):
        result = self.run_cli(
            "--schedule", str(self.schedule),
            "--overrides", str(self.overrides),
            "--from", "2026-11-06T17:00:00Z",
            "--until", "2026-11-06T17:00:00Z",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), [])

    def test_help(self):
        result = self.run_cli("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("--schedule", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_required_arguments(self):
        self.assert_cli_error(self.run_cli(), "required")

    def test_missing_file(self):
        self.schedule.unlink()
        self.assert_cli_error(self.render(), "cannot load schedule file")

    def test_invalid_json(self):
        self.overrides.write_text("[{", encoding="utf-8")
        self.assert_cli_error(self.render(), "cannot load overrides file")

    def test_invalid_encoding(self):
        self.schedule.write_bytes(b"\xff")
        self.assert_cli_error(self.render(), "cannot load schedule file")

    def test_invalid_schedule(self):
        self.schedule.write_text("{}", encoding="utf-8")
        self.assert_cli_error(self.render(), "schedule.users")

    def test_invalid_overrides(self):
        self.overrides.write_text("{}", encoding="utf-8")
        self.assert_cli_error(self.render(), "overrides must be a JSON array")

    def test_timestamp_without_timezone(self):
        self.assert_cli_error(
            self.render("--from=2026-11-06T17:00:00"), "timezone"
        )

    def test_reversed_query(self):
        self.assert_cli_error(
            self.render("--until=2026-11-05T17:00:00Z"), "until must be at or after from"
        )


if __name__ == "__main__":
    unittest.main()
