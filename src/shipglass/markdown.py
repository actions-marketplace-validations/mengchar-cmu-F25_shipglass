"""A bounded, metadata-only GitHub Markdown summary."""

from html import escape
import unicodedata


def _code(value: str) -> str:
    shortened = value[:200]
    label = "".join(
        {"\n": "\\n", "\r": "\\r", "\t": "\\t"}.get(char)
        or (f"\\u{ord(char):04x}" if ord(char) <= 0xFFFF else f"\\U{ord(char):08x}")
        if unicodedata.category(char).startswith("C") or char in "\u2028\u2029"
        else char
        for char in shortened
    )
    if len(value) > 200:
        label += "… [truncated]"
    # Entities keep both GFM tables and inline Markdown from interpreting names.
    label = escape(label).translate({ord(char): f"&#{ord(char)};" for char in "|`*_[]()!~\\:@"})
    return f"<code>{label}</code>"


def _bytes(value: int | None, signed: bool = False) -> str:
    if value is None:
        return "—"
    return (f"{value:+,d}" if signed and value else f"{value:,d}") + " B"


def render_markdown(comparison: dict) -> str:
    """Summarize releases without embedding payloads, hashes, or link targets."""
    before, after, summary = comparison["before"], comparison["after"], comparison["summary"]
    lines = [
        "# Shipglass release comparison",
        "",
        f"**Before:** {_code(before['name'])}",
        "",
        f"**After:** {_code(after['name'])}",
        "",
        "| Size | Before | After | Change |",
        "| --- | ---: | ---: | ---: |",
        f"| Expanded | {_bytes(summary['before_bytes'])} | {_bytes(summary['after_bytes'])} | {_bytes(summary['delta_bytes'], True)} |",
        f"| Archive | {_bytes(before['archive_bytes'])} | {_bytes(after['archive_bytes'])} | {_bytes(after['archive_bytes'] - before['archive_bytes'], True)} |",
        "",
        "| Added | Removed | Changed | Unchanged |",
        "| ---: | ---: | ---: | ---: |",
        f"| {summary['added']:,} | {summary['removed']:,} | {summary['changed']:,} | {summary['unchanged']:,} |",
        "",
        "## Changed paths",
        "",
    ]
    changes = sorted(
        (file for file in comparison["files"] if file["status"] != "unchanged"),
        key=lambda file: (-abs(file["delta"]), file["path"]),
    )
    if changes:
        lines.extend([
            f"Showing {min(10, len(changes)):,} of {len(changes):,} added, removed, or changed paths, ordered by absolute size change then path.",
            "",
            "| File | Status | Before | After | Change |",
            "| --- | --- | ---: | ---: | ---: |",
        ])
        for file in changes[:10]:
            lines.append(f"| {_code(file['path'])} | {file['status']} | {_bytes(file['before_size'])} | {_bytes(file['after_size'])} | {_bytes(file['delta'], True)} |")
        if len(changes) > 10:
            lines.extend(["", f"{len(changes) - 10:,} additional changed paths omitted."])
        same_size = sum(file["status"] == "changed" and file["delta"] == 0 for file in changes)
        if same_size:
            lines.extend(["", f"{same_size:,} modified paths have no size change; their contents or entry types differ."])
    else:
        lines.append("No added, removed, or changed paths.")

    archive_warnings = after.get("warnings", [])
    warning_count = len(archive_warnings)
    shown_warnings = [(after["name"], warning) for warning in archive_warnings[:10]]
    for file in after["files"]:
        warnings = file.get("warnings", [])
        warning_count += len(warnings)
        shown_warnings.extend((file["path"], warning) for warning in warnings[:max(0, 10 - len(shown_warnings))])
    lines.extend(["", "## Current release warnings", "", f"{warning_count:,} warnings in the after archive. Showing {len(shown_warnings):,} of {warning_count:,}.", ""])
    for path, warning in shown_warnings:
        lines.append(f"- {_code(path)}: {_code(warning['message'])} ({_code(warning['code'])})")
    if warning_count > 10:
        lines.extend(["", f"{warning_count - 10:,} additional warnings omitted."])
    lines.extend([
        "",
        "Filename warnings are heuristics, not secret detection or a security audit. Review flagged names and entry metadata before publishing.",
        "",
        "Sizes are exact bytes. Labels longer than 200 characters are marked truncated. No file contents, hashes, or link targets are included.",
        "",
    ])
    return "\n".join(lines)
