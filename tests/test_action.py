import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "action.py"


class ActionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="shipglass action ")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.runner_temp = self.root / "runner temp"
        self.runner_temp.mkdir()
        self.output = self.root / "github output"
        self.summary = self.root / "github summary"
        self.before = self.archive("before.zip", {"file": b"a"})
        self.after = self.archive("after.zip", {"file": b"abc"})

    def archive(self, name, files):
        path = self.root / name
        with zipfile.ZipFile(path, "w") as archive:
            for member, content in files.items():
                archive.writestr(member, content)
        return path

    def run_action(self, **overrides):
        env = {key: value for key, value in os.environ.items() if not key.startswith("SHIPGLASS_")}
        env.update({"SHIPGLASS_BEFORE": str(self.before), "SHIPGLASS_AFTER": str(self.after), "RUNNER_TEMP": str(self.runner_temp), "GITHUB_OUTPUT": str(self.output), "GITHUB_STEP_SUMMARY": str(self.summary)})
        env.update(overrides)
        return subprocess.run([sys.executable, str(SCRIPT)], cwd=self.root, env=env, text=True, capture_output=True)

    def outputs(self):
        lines = self.output.read_text(encoding="utf-8").splitlines()
        values = {}
        while lines:
            key, delimiter = lines.pop(0).split("<<", 1)
            value = []
            while lines[0] != delimiter:
                value.append(lines.pop(0))
            lines.pop(0)
            values[key] = "\n".join(value)
        return values

    def test_success_produces_only_reports_and_summary(self):
        process = self.run_action()
        self.assertEqual(process.returncode, 0, process.stderr)
        output = self.outputs()
        directory = Path(output["report-directory"])
        self.assertEqual(directory.parent, self.runner_temp)
        self.assertEqual({path.name for path in directory.iterdir()}, {"report.html", "report.json", "report.md"})
        self.assertEqual(output["default-artifact-name"], directory.name)
        for key in ("report-path", "json-path", "markdown-path"):
            self.assertTrue(Path(output[key]).is_file())
        self.assertEqual(output["check-result"], "passed")
        self.assertEqual(output["delta-bytes"], "2")
        self.assertEqual(output["warning-count"], "0")
        self.assertIn("Policy checks: passed", self.summary.read_text(encoding="utf-8"))

    def test_policy_failure_retains_reports_and_returns_zero(self):
        process = self.run_action(SHIPGLASS_MAX_GROWTH_BYTES="1")
        self.assertEqual(process.returncode, 0, process.stderr)
        output = self.outputs()
        self.assertEqual(output["check-result"], "failed")
        self.assertTrue(Path(output["report-path"]).is_file())
        self.assertIn("Policy checks: failed", self.summary.read_text(encoding="utf-8"))
        process = self.run_action(SHIPGLASS_MAX_GROWTH_BYTES="2")
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(self.outputs()["check-result"], "passed")

    def test_repeated_invocations_have_distinct_outputs(self):
        self.assertEqual(self.run_action().returncode, 0)
        first = self.outputs()
        self.assertEqual(self.run_action().returncode, 0)
        second = self.outputs()
        self.assertNotEqual(first["report-directory"], second["report-directory"])
        self.assertNotEqual(first["default-artifact-name"], second["default-artifact-name"])
        self.assertTrue(Path(first["report-path"]).is_file())

    def test_paths_with_spaces_and_shell_metacharacters_are_literal(self):
        before = self.archive("-before $(echo injected) & ' old.zip", {"file": b"a"})
        after = self.archive("after `echo injected` & new.zip", {"file": b"abc"})
        process = self.run_action(SHIPGLASS_BEFORE=before.name, SHIPGLASS_AFTER=after.name)
        self.assertEqual(process.returncode, 0, process.stderr)
        result = json.loads(Path(self.outputs()["json-path"]).read_text(encoding="utf-8"))
        self.assertEqual(result["before"]["name"], before.name)
        self.assertEqual(result["after"]["name"], after.name)

    def test_current_warnings_exclude_removed_files(self):
        before = self.archive("cautions.zip", {".env": b"synthetic", "file": b"a"})
        process = self.run_action(SHIPGLASS_BEFORE=str(before), SHIPGLASS_FAIL_ON_WARNINGS="true")
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(self.outputs()["warning-count"], "0")
        self.assertEqual(self.outputs()["check-result"], "passed")
        process = self.run_action(SHIPGLASS_AFTER=str(before), SHIPGLASS_FAIL_ON_WARNINGS="true")
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(self.outputs()["warning-count"], "1")
        self.assertEqual(self.outputs()["check-result"], "failed")

    def test_strip_components_reuses_cli(self):
        before = self.archive("old.zip", {"old/file": b"same"})
        after = self.archive("new.zip", {"new/file": b"same"})
        process = self.run_action(SHIPGLASS_BEFORE=str(before), SHIPGLASS_AFTER=str(after), SHIPGLASS_STRIP_COMPONENTS="1")
        self.assertEqual(process.returncode, 0, process.stderr)
        result = json.loads(Path(self.outputs()["json-path"]).read_text(encoding="utf-8"))
        self.assertEqual(result["summary"]["unchanged"], 1)

    def test_bad_archive_has_no_success_outputs_or_summary(self):
        bad = self.root / "bad.zip"
        bad.write_bytes(b"not an archive")
        process = self.run_action(SHIPGLASS_AFTER=str(bad))
        self.assertEqual(process.returncode, 2)
        self.assertFalse(self.output.exists())
        self.assertFalse(self.summary.exists())

    def test_invalid_options_have_no_outputs(self):
        invalid = [{"SHIPGLASS_BEFORE": ""}, {"SHIPGLASS_AFTER": ""}, {"SHIPGLASS_MAX_GROWTH_BYTES": "-1"}, {"SHIPGLASS_MAX_GROWTH_BYTES": "1.5"}, {"SHIPGLASS_STRIP_COMPONENTS": "-1"}, {"SHIPGLASS_STRIP_COMPONENTS": ""}, {"SHIPGLASS_FAIL_ON_WARNINGS": "True"}, {"SHIPGLASS_FAIL_ON_WARNINGS": "anything"}]
        for options in invalid:
            with self.subTest(options=options):
                process = self.run_action(**options)
                self.assertEqual(process.returncode, 2)
                self.assertFalse(self.output.exists())
                self.assertFalse(self.summary.exists())
        self.assertEqual(list(self.runner_temp.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
