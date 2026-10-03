# Validation notes

The initial release was exercised on macOS with Python 3.12, using the unit tests in
`tests/`, an isolated installation of the built wheel, and the browser report.
GitHub Actions defines a Linux, macOS, and Windows matrix for Python 3.10, 3.12,
and 3.13; see the live Actions results for its current status.

Browser checks covered search, status filtering, sorting, before/after snapshots,
file details, empty results, and a narrow mobile viewport. The report loads no
remote scripts, fonts, or stylesheets. HTML serialization tests include hostile
script delimiters in filenames.

Two public package pairs were downloaded from their official registries and scanned
without executing or installing their contents:

| Artifacts | Before payload | After payload | Observed changes |
| --- | ---: | ---: | --- |
| `six` 1.16.0 → 1.17.0 wheels from PyPI | 37,959 B | 37,975 B | 1 changed, 5 added, 5 removed |
| `is-number` 6.0.0 → 7.0.0 tarballs from npm | 8,960 B | 9,615 B | 4 changed |

The wheel's version-specific `.dist-info` directory changes its paths, so those
members appear as added and removed. This is intentional path-based comparison.

The built-in Orbit UI example is synthetic. Repetitive fixture payloads make its
compressed archives much smaller than typical real-world JavaScript packages.
Its 6 MiB source map illustrates expanded size growth, not a measured production
incident or actual credential leak.
