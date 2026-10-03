# Compare published npm versions

Prepare Python 3.10 or newer and [install Shipglass](../README.md#try-it) first, or use the [GitHub Actions workflow](#run-in-github-actions) below without a local installation.

With Shipglass 0.3.0 or newer, one command downloads and compares two public npm releases:

```sh
shipglass npm vite 6.0.0 7.0.0 -o vite.html
```

Open `vite.html` locally. No Node.js or npm installation is needed. Shipglass downloads the published tarballs, checks their registry-provided digests, and reads the archive entries without installing packages, fetching dependencies, or running lifecycle scripts.

Use a complete version number for each side. Scoped package names are supported:

```sh
shipglass npm @types/node 22.0.0 22.1.0 \
  -o node-types.html --json node-types.json --markdown node-types.md
```

Tags such as `latest`, version ranges such as `^7`, URLs, private packages, and custom registries are unsupported. Shipglass does not choose a baseline or resolve your dependency tree.

## The same reports and checks

All comparison options apply, including `--strip-components`, `--fail-on-growth`, and `--fail-on-warnings`:

```sh
shipglass npm vite 6.0.0 7.0.0 \
  -o vite.html --markdown vite.md --fail-on-growth 1000000
```

A configured check uses expanded file bytes and current-release filename cautions. Exit code 0 means the comparison completed without violating a configured check. Exit code 1 means a check failed, with reports still written. Download or archive errors return 2 without producing a new report. Existing output files are not deleted when a download fails.

For these Vite versions, the measured expanded payload decreases from 2,804,531 to 2,267,804 bytes. The [reproducible Vite example](examples/vite.md) shows the same comparison using manually downloaded local archives. These totals exclude installed dependencies and do not measure application bundle size or performance.

## Run in GitHub Actions

The [Compare published package releases workflow](https://github.com/mengchar-cmu-F25/shipglass/actions/workflows/npm.yml) runs the same CLI command and saves HTML, JSON, and Markdown reports. Repository maintainers can select **Run workflow**, keep the registry set to **npm**, then enter the package name, exact baseline version, and exact current version. The defaults compare Vite 6.0.0 with 7.0.0. Running a workflow requires write access to its repository.

To run it in your own repository, copy [`.github/workflows/npm.yml`](../.github/workflows/npm.yml) to the same path on your default branch, then open your repository's Actions tab and select **Compare published package releases → Run workflow**. The workflow prepares Python 3.12 and installs the published Shipglass v0.4.0 wheel before invoking the CLI. It does not need checkout, Node.js, or npm. You choose both versions; it does not infer a baseline from your project, install either package, or execute package scripts. The same workflow also supports [PyPI wheels](pypi.md#run-in-github-actions).

After the run, read the job summary or download the `package-release-diff` artifact and open `report.html` locally. GitHub requires sign-in and repository access to download workflow artifacts. By default, the comparison records changes without failing on growth or filename cautions. To enforce a limit, append an existing CLI option such as `--fail-on-growth 1000000` or `--fail-on-warnings` to the comparison command in your copy of the workflow.

See a [completed Vite comparison](https://github.com/mengchar-cmu-F25/shipglass/actions/runs/37133401505) using this workflow and the published v0.4.0 wheel. Its report records the same 536,727-byte reduction as the local example.

If a configured check fails, the comparison step fails but the summary and upload steps still preserve its reports. Download, validation, or archive errors fail the job without producing a new report. The summary step only reads an existing `report.md`, and the upload step ignores absent reports; neither converts a failed comparison into a successful job. These steps are skipped if the workflow is cancelled.

## Network and storage

The `npm` and [`pypi`](pypi.md) commands explicitly opt into downloading. The `compare`, `inspect`, and `demo` commands remain offline. The npm command requests the package names and versions you enter from `registry.npmjs.org`, using its [version metadata API](https://github.com/npm/registry/blob/main/docs/REGISTRY-API.md#getpackageversion). It accepts tarballs and redirects only on that registry over HTTPS and does not load npm credentials or `.npmrc` configuration.

Metadata responses are limited to 1 MiB. Downloads are limited to 1 GiB per archive, and the normal [archive scanning limits](../README.md#compare-what-you-ship) still apply. A failed download, digest mismatch, invalid metadata response, or unsupported archive stops the comparison. Downloaded archives are temporary and are removed after the command completes or reports an error; generated reports stay at the paths you selected.

Reports contain file paths and metadata, not package source contents. They are written locally and work offline. The command does not upload a report or your project files. To compare private or pre-release build outputs, prepare the archives yourself and use `shipglass compare before.tgz after.tgz`.
