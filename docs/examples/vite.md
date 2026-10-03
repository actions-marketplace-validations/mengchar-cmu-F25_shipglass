# Vite 6.0.0 → 7.0.0

[Open the interactive report](https://mengchar-cmu-f25.github.io/shipglass/?example=vite).

This comparison uses the published npm archives for exactly **Vite 6.0.0** and **Vite 7.0.0**, downloaded from the official npm registry. It was generated with Shipglass 0.2.0 on October 3, 2026. Package contents were read without installing Vite, running package scripts, or extracting files.

## Reproduce

With Shipglass 0.3.0 or newer, the same published versions can be compared directly:

```sh
shipglass npm vite 6.0.0 7.0.0 -o vite.html
```

The command downloads the archives without installing Vite. See the [npm guide](../npm.md) for network behavior and limits. The original manual recipe below also works with version 0.2.0 and separates the download step from the offline comparison.

With Shipglass 0.2.0 installed, run these commands in a POSIX shell. They create a fresh temporary directory, download the two archives, and write HTML, JSON, and Markdown reports:

```sh
vite_example_dir=$(mktemp -d)
cd "$vite_example_dir"

curl --fail --location --output vite-6.0.0.tgz \
  https://registry.npmjs.org/vite/-/vite-6.0.0.tgz
curl --fail --location --output vite-7.0.0.tgz \
  https://registry.npmjs.org/vite/-/vite-7.0.0.tgz

shipglass compare vite-6.0.0.tgz vite-7.0.0.tgz \
  --output vite.html --json vite.json --markdown vite-summary.md
```

The download URLs are the `dist.tarball` values in the registry metadata for [Vite 6.0.0](https://registry.npmjs.org/vite/6.0.0) and [Vite 7.0.0](https://registry.npmjs.org/vite/7.0.0). No prefix stripping is needed: both archives use `package/`.

## Observed result

| Measure | Vite 6.0.0 | Vite 7.0.0 | Change |
| --- | ---: | ---: | ---: |
| Compressed archive bytes | 668,455 | 548,445 | −120,010 |
| Expanded payload bytes | 2,804,531 | 2,267,804 | −536,727 (−19.1%) |
| Files | 34 | 39 | +5 |

Shipglass reports **13 added, 8 removed, 20 changed, and 6 unchanged** paths. Expanded sizes and file counts agree with the registry's `dist.unpackedSize` and `dist.fileCount` for both versions.

The largest removal is `package/dist/node/chunks/dep-C6qYk3zB.js` at **1,601,961 bytes**; the largest addition is `package/dist/node/chunks/dep-Bsx9IwL8.js` at **1,351,742 bytes**. The chunk filenames differ, so they appear as separate removed and added paths. Shipglass does not establish a rename or a one-to-one relationship between them.

Other concrete observations:

- `package/dist/node-cjs/publicUtils.cjs` is removed: **166,888 bytes**.
- `package/index.cjs` and `package/index.d.cts` are also removed. Vite's [7.0 announcement](https://vite.dev/blog/announcing-vite7#node-js-support) documents the move to an ESM-only distribution and its Node.js requirements.
- At the unchanged path `package/dist/node/index.d.ts`, content changes and size falls from **148,731 to 143,791 bytes**.
- The current archive has **zero packaging cautions** under Shipglass's filename checks. That result provides no assessment of package security or correctness.

These totals describe the contents of two npm tarballs. They exclude installed dependency trees and do not measure application bundle size, build speed, runtime behavior, or compatibility. Size differences alone do not establish a regression or an improvement; use the report to choose files to investigate and consult Vite's release notes when assessing an upgrade.
