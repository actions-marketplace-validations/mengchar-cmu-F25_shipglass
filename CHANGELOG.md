# Changelog

## 0.4.2 — 2026-10-03

- Add an **All changes** report filter that shows added, removed, and changed paths together, excluding unchanged files.
- Keep equal-size content changes and zero-byte file additions/removals visible in this filter. Search, snapshots, and pagination continue to work together.
- Refresh all four public example reports with the new filter.

## 0.4.1 — 2026-10-03

- Include `scripts/action.py` in the source distribution so its bundled Action tests can run after installing from the source archive.

## 0.4.0 — 2026-10-03

- Compare two exact public PyPI releases with `shipglass pypi PACKAGE BEFORE_VERSION AFTER_VERSION` when each has one unambiguous, non-yanked universal Python 3 wheel.
- Verify the published SHA-256 and archive size, bound downloads, and remove temporary wheels without installing or executing their contents.
- Reject ambiguous, platform-specific, missing, or yanked wheels with guidance for explicit local archive comparison.
- Reproduce the Rich example in one command with the same HTML, JSON, Markdown, and optional checks as npm comparisons.
- Add a TypeScript 4.9.5 → 5.0.4 case study and compare Shipglass's own built wheel with an explicitly selected release in CI.

## 0.3.2 — 2026-10-03

- Sort the file manifest by the largest size across both releases, including removed and newly added files, independently of the treemap snapshot.
- Clarify the size-sort option and refresh the public example reports with the corrected ordering.
- Return to the file manifest heading after changing pages, including keyboard focus, so reviewers can read the next files without scrolling back manually.
- Add a manual GitHub workflow that compares a public npm package's two exact versions and saves its report and job summary.

## 0.3.1 — 2026-10-03

- Reject gzip-compressed TAR archives with damaged checksums, incorrect expanded-size trailers, or missing trailers instead of reporting a successful scan.
- Apply the expanded TAR stream limit to the entire input, including bytes after the TAR end marker.
- Keep invalid inputs from producing HTML, JSON, or Markdown reports.

## 0.3.0 — 2026-10-03

- Compare two exact public npm versions with `shipglass npm PACKAGE BEFORE_VERSION AFTER_VERSION`.
- Download archives into temporary storage, verify their registry-provided digests, and remove downloads after comparison.
- Support scoped packages, existing report formats, prefix stripping, and optional growth or packaging-caution checks.
- Keep local-file commands offline; the new command explicitly contacts the public npm registry and never installs or runs package contents.

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
