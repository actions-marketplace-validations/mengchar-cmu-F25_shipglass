# Roadmap

Shipglass starts with a small, usable loop: compare two local release archives, read the report, and understand what changed. These are priorities, not release-date commitments.

## First: make the core dependable

- Gather reproducible examples from npm tarballs, Python wheels, and generic ZIP/TAR archives.
- Fix parsing or path-handling gaps with focused regression tests.
- Improve report navigation using feedback from actual package comparisons, including empty archives and packages with many files.
- Make size units, compression effects, file statuses, and filename cautions clear.
- Keep installation and demo instructions verified against the packaged CLI.

## Next: reduce release-review friction

- Add a short GitHub Actions example that saves reports as workflow artifacts.
- Consider a command that snapshots a local npm package with lifecycle scripts explicitly disabled.
- Consider Markdown summaries for CI systems that can link to an HTML report.
- Consider directory input when a concrete build workflow needs it.

## Later, if examples justify it

- Separate prefix mapping for each archive when the existing shared `--strip-components` option cannot express the comparison.
- File-move suggestions, with clear separation from confirmed content changes.
- More archive formats and richer package metadata.
- Accessibility and navigation improvements informed by larger real-world reports.

## Outside the current plan

Hosted dashboards, accounts, telemetry, automatic registry downloads, general secret scanning, and deep binary analysis are outside the current scope. The project should remain useful as a local command and an HTML file.

To suggest a feature, describe the release workflow, include a small example if possible, and explain what the current report makes difficult. Start a [GitHub issue](https://github.com/mengchar-cmu-F25/shipglass/issues).
