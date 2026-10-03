"""Render a portable report containing metadata, never archive contents."""

from importlib.resources import files
import json


def render_report(comparison: dict) -> str:
    """Return a self-contained HTML report for a comparison."""
    def snapshot(value: dict) -> dict:
        result = {
            key: value.get(key)
            for key in ("name", "archive_bytes", "total_bytes", "format")
        }
        inventory = value.get("files", 0)
        result["files"] = len(inventory) if isinstance(inventory, (list, dict)) else inventory
        return result

    data = {
        "schema_version": comparison.get("schema_version", 1),
        "before": snapshot(comparison["before"]),
        "after": snapshot(comparison["after"]),
        "summary": comparison["summary"],
        "files": [
            {
                key: entry.get(key)
                for key in ("path", "status", "before_size", "after_size", "delta", "warnings")
            }
            for entry in comparison["files"]
        ],
        "warnings": comparison.get("warnings", []),
    }
    # HTML parsers recognize closing script tags even inside JSON strings.
    payload = json.dumps(data, ensure_ascii=True, separators=(",", ":"))
    payload = payload.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    template = files("shipglass").joinpath("report.html").read_text(encoding="utf-8")
    return template.replace("__SHIPGLASS_DATA__", payload)
