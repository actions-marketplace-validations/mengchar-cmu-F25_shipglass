# Validation notes

The initial release was exercised on macOS with Python 3.12, using the unit tests in
`tests/`, an isolated installation of the built wheel, and the browser report.
GitHub Actions defines a Linux, macOS, and Windows matrix for Python 3.10, 3.12,
and 3.13; see the live Actions results for its current status.

Browser checks covered search, status filtering, sorting, before/after snapshots,
file details, empty results, and a narrow mobile viewport. The report loads no
remote scripts, fonts, or stylesheets. HTML serialization tests include hostile
script delimiters in filenames.

Five public package pairs were downloaded from their official registries and scanned
without executing or installing their contents:

| Artifacts | Before payload | After payload | Observed changes |
| --- | ---: | ---: | --- |
| `six` 1.16.0 → 1.17.0 wheels from PyPI | 37,959 B | 37,975 B | 1 changed, 5 added, 5 removed |
| `is-number` 6.0.0 → 7.0.0 tarballs from npm | 8,960 B | 9,615 B | 4 changed |
| [`vite` 6.0.0 → 7.0.0 tarballs from npm](examples/vite.md) | 2,804,531 B | 2,267,804 B | 20 changed, 13 added, 8 removed |
| [`rich` 13.9.4 → 14.0.0 wheels from PyPI](examples/rich.md) | 955,765 B | 959,611 B | 7 changed, 4 added, 4 removed |
| [`typescript` 4.9.5 → 5.0.4 tarballs from npm](examples/typescript.md) | 66,849,652 B | 39,203,145 B | 95 changed, 6 added, 7 removed |

The wheel's version-specific `.dist-info` directory changes its paths, so those
members appear as added and removed. This is intentional path-based comparison.

The Vite and Rich comparisons were generated with version 0.2.0. Their linked
recipes record exact versions, official registry sources, and download and
comparison commands. The [live demo](https://mengchar-cmu-f25.github.io/shipglass/)
allows switching between the real examples and the synthetic one. The TypeScript
comparison was generated with version 0.3.2. Its expanded byte totals and file
counts match npm registry metadata for the two exact versions.

Version 0.3.0's `npm` command was also exercised from an isolated installation of
its built wheel against the public registry. `vite 6.0.0 7.0.0` reproduced the
manual comparison's exact expanded byte totals. The scoped-package example
`@types/node 22.0.0 22.1.0` completed with 8 changed paths and a 494-byte decrease.
Both produced HTML, JSON, and Markdown reports without installing the downloaded
packages. Offline tests cover download limits, registry responses, digest checks,
redirect restrictions, errors, and temporary-file cleanup.

Version 0.3.1 adds regression coverage for damaged gzip CRC and size trailers,
missing trailers, and TAR padding beyond the end marker. The expanded-stream
limit accepts an input exactly at the limit and rejects one byte more. All 81
tests passed locally. An isolated installation of the built wheel reproduced the
Vite byte totals above and returned exit code 2 for a corrupted gzip fixture,
without generating HTML, JSON, or Markdown reports.

Version 0.3.2 was checked in a browser with added, removed, growing, and shrinking
files: largest-file order stays the same when switching treemap snapshots.
Checks covered desktop and 390-pixel layouts, plus forward/backward navigation
and keyboard focus across an 83-file manifest. The built wheel produced exactly
the same report as the source checkout. The manual npm workflow was also run on
GitHub: its [Vite comparison](https://github.com/mengchar-cmu-F25/shipglass/actions/runs/37130884917)
produced the three expected reports and the byte totals above. An intentional
[`latest` input rejection](https://github.com/mengchar-cmu-F25/shipglass/actions/runs/37130952938)
failed the job without uploading a report.

The built-in Orbit UI example is synthetic. Repetitive fixture payloads make its
compressed archives much smaller than typical real-world JavaScript packages.
Its 6 MiB source map illustrates expanded size growth, not a measured production
incident or actual credential leak.

The project's own [wheel comparison run](https://github.com/mengchar-cmu-F25/shipglass/actions/runs/37132406849)
compared its built candidate with the published v0.3.2 wheel. All nine build/install/test
jobs passed. Its downloaded `shipglass-wheel-diff` artifact contained exactly HTML,
JSON, and Markdown reports; the comparison correctly identified the README-driven
`METADATA` change and its updated `RECORD` entry.

Version 0.4.0 adds the PyPI command. All 99 tests passed locally, including wheel
selection, digest/size checks, host restrictions, download failures, cleanup, and
CLI reports and exit codes. A real Rich 13.9.4 → 14.0.0 run reproduced every file
change and byte total in the earlier manual example. `Typing_Extensions 4.12.2`
compared with itself downloaded once and produced no changes. NumPy 2.2.0 (no
universal Python 3 wheel) and the Rich `14.0` version alias both returned exit 2
without generating a report.
