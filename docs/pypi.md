# Compare published Python wheels

With Python 3.10 or newer and Shipglass 0.4.0 or newer, compare two exact public PyPI releases in one command:

```sh
shipglass pypi rich 13.9.4 14.0.0 \
  -o rich.html --json rich.json --markdown rich-summary.md
```

Open `rich.html` locally. Shipglass selects one universal Python 3 wheel for each release, checks its published SHA-256 and size, and compares its archive entries. It does not install the wheels, fetch dependencies, or run package code. The [Rich example](examples/rich.md) records the measured 955,765 → 959,611 byte payload change.

## Which releases work?

Each release must publish exactly one non-yanked wheel tagged `py3-none-any` or a compatible compressed tag such as `py2.py3-none-any`. These wheels contain Python code without a platform-specific ABI. This command inspects their contents; it does not check whether your interpreter satisfies their `Requires-Python` metadata.

The command does not choose between operating systems, Python interpreter versions, or multiple wheel build numbers. Native wheels, source-only releases, multiple eligible wheels, and releases with only yanked eligible wheels return an error. To compare those releases, download the two specific archives you intend to review and use `shipglass compare before.whl after.whl`. Source archives can also be compared directly; Shipglass does not build them.

Use the exact version spelling published by PyPI. For example, request `14.0.0`, not an alias such as `14.0` or `v14.0.0`. Version ranges, `latest`, URLs, private indexes, and credentials are unsupported. Project names follow [PyPA normalization](https://packaging.python.org/en/latest/specifications/name-normalization/), so `typing_extensions` and `typing-extensions` refer to the same project.

Wheel `.dist-info` directories include the version. Their paths appear as additions and removals when the version changes, even when some metadata contents are identical. Paths are matched exactly; no rename inference is applied.

## Reports and checks

The existing comparison options work with `pypi`, including `--strip-components`, `--fail-on-growth`, and `--fail-on-warnings`:

```sh
shipglass pypi rich 13.9.4 14.0.0 \
  -o rich.html --markdown rich.md --fail-on-growth 10000
```

Exit code 0 means the comparison completed without violating a configured check. Exit code 1 means a check failed, with reports still written. Download, selection, integrity, and archive errors return 2 without producing a new report. Existing output files are preserved on download failure. Growth is measured in expanded file bytes, not compressed wheel size or installed dependency size.

For a candidate wheel built in your own project, use the [Python build workflow](github-actions.md#review-a-python-wheel-before-release). It compares local artifacts before publishing them.

## Network and storage

This command explicitly contacts public PyPI using its [release JSON API](https://docs.pypi.org/api/json/#get-a-release). Metadata requests and redirects are restricted to HTTPS `pypi.org`; wheel downloads and redirects are restricted to HTTPS `files.pythonhosted.org`. Shipglass does not read pip configuration or credentials.

Metadata is limited to 1 MiB and each archive to 1 GiB. The published archive size is also enforced while downloading, before checking SHA-256. The normal [archive scanning limits](../README.md#compare-what-you-ship) still apply. Downloaded wheels are temporary and are removed on success or failure. Generated reports remain where you saved them and work offline.

The `compare`, `inspect`, and `demo` commands remain offline. The `npm` and `pypi` commands download only when explicitly invoked. No CLI command uploads reports or project files.
