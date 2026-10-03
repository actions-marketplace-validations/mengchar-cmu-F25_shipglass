# Roadmap

Shipglass starts with a small, usable loop: compare two local release archives, read the report, and understand what changed. These are priorities, not release-date commitments.

## Shipped

- Compare local release archives and inspect file changes in an offline HTML report.
- Export JSON and opt into checks for expanded payload growth or packaging cautions.
- Remove shared wrapper directories with explicit `--strip-components` path matching.
- Generate compact Markdown summaries for CI systems and release reviews.
- Use the [GitHub Action](github-actions.md) to add a job summary and save reports, including when a configured check fails.
- Download and compare two exact public npm versions with the explicit [`npm` command](npm.md).

## Next: validate real release workflows

- Gather reproducible examples from npm tarballs, Python wheels, and generic ZIP/TAR archives.
- Fix parsing or path-handling gaps with focused regression tests.
- Improve report navigation using feedback from actual package comparisons, including empty archives and packages with many files.
- Document baseline selection and build steps for a concrete npm or Python release workflow.
- Keep installation, demo, and Action examples verified against released versions.

## Later, if examples justify it

- Consider a command that snapshots a local npm package with lifecycle scripts explicitly disabled.
- Consider directory input when a concrete build workflow needs it.
- Separate prefix mapping for each archive when the existing shared `--strip-components` option cannot express the comparison.
- File-move suggestions, with clear separation from confirmed content changes.
- More archive formats and richer package metadata.
- Accessibility and navigation improvements informed by larger real-world reports.

## Outside the current plan

Hosted dashboards, accounts, telemetry, automatic baseline selection, private registry credentials, general secret scanning, and deep binary analysis are outside the current scope. The project should remain useful as a local command and an HTML file.

To suggest a feature, describe the release workflow, include a small example if possible, and explain what the current report makes difficult. Start a [GitHub issue](https://github.com/mengchar-cmu-F25/shipglass/issues).
