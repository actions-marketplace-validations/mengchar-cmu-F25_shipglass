# What Shipglass is for

Shipglass answers a focused release-review question:

**What changed inside these two archives, and where did the extra bytes come from?**

Source changes do not always make the final package contents obvious. Build outputs, packaging rules, generated data, and leftover files can all change the artifact that reaches a user. Shipglass reads that artifact and presents file changes in an offline report.

## The first use cases

- Review an npm tarball or Python wheel before publishing it.
- Explain an unexpected increase in release size.
- Check which files appeared or disappeared between builds.
- Attach an HTML report to a CI run for someone who does not have the archives locally.

The report includes filenames, sizes, comparison status, and packaging cautions. It does not include the archived file contents. Private filenames can still be sensitive.

## Existing tools and boundaries

These projects already address related problems. The descriptions below summarize their own documentation; they are not a benchmark or an exhaustive feature comparison.

| Tool | Documented focus | Where Shipglass fits |
| --- | --- | --- |
| [diffoscope](https://diffoscope.org/) | Deep recursive comparison of archives, directories, and many binary formats; text and HTML output. | A smaller file-level overview with size visualization, intended for a quick release check. |
| [PkgDiff](https://github.com/lvc/pkgdiff) | Visualizing changes in Linux software packages, including compatibility review. | A Python standard-library tool for common application release archives. |
| [publishcanary](https://github.com/diegosantdev/publishcanary) | npm publishing checks, including content-based secret patterns and package comparisons. | Local archive comparison across npm, Python wheels, and generic ZIP/TAR files, with filename cautions only. |
| [almeidx/diff](https://github.com/almeidx/diff) | Visual comparisons between versions of npm packages and WordPress plugins. | An offline workflow starting from files already on disk. |

Shipglass does not aim to replace these tools. Its design priorities are a quick local run, a readable self-contained report, explicit limits, and useful output without a service or account.

## Current boundaries

- Local `.zip`, `.whl`, `.tar`, `.tgz`, and `.tar.gz` inputs.
- Explicit `npm` and `pypi` commands can download two exact public releases for comparison, without package installation or script execution. PyPI selection is limited to unambiguous universal Python 3 wheels.
- Match members by their paths inside the archives, with optional explicit `--strip-components N` applied to both inputs.
- Compare file content using SHA-256, including same-size changes.
- Report added, removed, changed, and unchanged files.
- Show packaging cautions based on filenames, without reading secret values into reports.
- No private registries, automatic baseline selection, directory comparison, semantic code diff, timestamp or permission comparison, rename detection, recursive archive inspection, or binary compatibility analysis.

Large or unusual archives may hit reader limits. The command reports an error rather than presenting a partial comparison as complete.

## Evidence before expansion

The next features should follow real examples: a package the reader cannot handle, a report that obscures the important change, or a repetitive release step that the CLI can simplify. Popularity is not evidence that a feature solves those problems.
