# Changelog

## 0.2.0 — 2026-10-03

- Add a GitHub Action for local release archives, with a job summary and downloadable HTML, JSON, and Markdown reports.
- Save Action reports before failing an optional expanded-size or packaging-caution check.
- Add `--markdown PATH` to `compare`, `inspect`, and `demo` for compact summaries of sizes, changed paths, and current-release cautions.
- Keep Markdown summaries bounded and escape archive-provided labels without including file contents, hashes, or link targets.
- Document Action inputs, outputs, runner requirements, report privacy, and a complete workflow.

## 0.1.0 — 2026-10-03

- Compare ZIP, Python wheel, TAR, and gzip-compressed TAR release archives.
- Explore file sizes, additions, removals, and content changes in a single offline HTML report.
- Search, sort, filter, switch snapshots, and inspect individual files.
- Export JSON and opt into CI checks for unpacked growth or packaging cautions.
- Inspect a single archive or run the deterministic synthetic demo.
- Bound archive reading, keep link targets private, and never extract or execute archive contents.

The first release compares file payloads and entry types. Permission modes, timestamps,
rename detection, nested archives, and format-aware content diffs are outside its scope.
