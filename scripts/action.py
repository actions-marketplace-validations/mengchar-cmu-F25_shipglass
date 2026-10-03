"""Run the bundled CLI inside a GitHub composite action."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from shipglass.cli import _display, main as cli_main


def _number(name: str, default: str = "") -> int | None:
    value = os.environ.get(name, default)
    if value == "" and default == "":
        return None
    if not value.isascii() or not value.isdecimal():
        raise ValueError(f"{name} must be a non-negative integer")
    return int(value)


def _outputs(values: dict[str, object]) -> str:
    result = []
    for key, value in values.items():
        delimiter = "shipglass_" + uuid.uuid4().hex
        result.append(f"{key}<<{delimiter}\n{value}\n{delimiter}\n")
    return "".join(result)


def main() -> int:
    try:
        before = os.environ.get("SHIPGLASS_BEFORE", "")
        after = os.environ.get("SHIPGLASS_AFTER", "")
        if not before or not after:
            raise ValueError("SHIPGLASS_BEFORE and SHIPGLASS_AFTER are required")
        before, after = str(Path(before).resolve()), str(Path(after).resolve())
        growth_limit = _number("SHIPGLASS_MAX_GROWTH_BYTES")
        strip_components = _number("SHIPGLASS_STRIP_COMPONENTS", "0")
        fail_on_warnings = os.environ.get("SHIPGLASS_FAIL_ON_WARNINGS", "false")
        if fail_on_warnings not in ("true", "false"):
            raise ValueError("SHIPGLASS_FAIL_ON_WARNINGS must be exactly true or false")
        directory = Path(tempfile.mkdtemp(prefix="shipglass-", dir=os.environ.get("RUNNER_TEMP") or None))
        html_path = directory / "report.html"
        json_path = directory / "report.json"
        markdown_path = directory / "report.md"
        arguments = ["compare", before, after, "--output", str(html_path), "--json", str(json_path), "--markdown", str(markdown_path), "--strip-components", str(strip_components)]
        if growth_limit is not None:
            arguments += ["--fail-on-growth", str(growth_limit)]
        if fail_on_warnings == "true":
            arguments.append("--fail-on-warnings")
        code = cli_main(arguments)
        if code not in (0, 1):
            return 2
        if not all(path.is_file() for path in (html_path, json_path, markdown_path)):
            raise ValueError("Comparison did not produce all three reports")
        result = json.loads(json_path.read_text(encoding="utf-8"))
        current_warnings = len(result["after"]["warnings"]) + sum(len(item["warnings"]) for item in result["after"]["files"])
        check_result = "passed" if code == 0 else "failed"
        explanation = "No configured blocking policy was violated." if code == 0 else "A configured growth or packaging-caution policy was violated. Reports are available for review; the action will fail after uploading them."
        summary = markdown_path.read_text(encoding="utf-8").rstrip() + f"\n\n**Policy checks: {check_result}.** {explanation}\n"
        output = _outputs({"report-path": html_path, "json-path": json_path, "markdown-path": markdown_path, "report-directory": directory, "default-artifact-name": directory.name, "delta-bytes": result["summary"]["delta_bytes"], "warning-count": current_warnings, "check-result": check_result})
        if os.environ.get("GITHUB_STEP_SUMMARY"):
            with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as stream:
                stream.write(summary)
        if os.environ.get("GITHUB_OUTPUT"):
            with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as stream:
                stream.write(output)
        return 0
    except (OSError, ValueError) as error:
        print(f"shipglass action: {_display(error)}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
