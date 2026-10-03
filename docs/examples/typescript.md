# TypeScript 4.9.5 → 5.0.4

[Open the interactive report](https://mengchar-cmu-f25.github.io/shipglass/?example=typescript) to explore a **27,646,507-byte reduction** in the expanded npm package.

This reproduces an optimization documented in Microsoft's [TypeScript 5.0 announcement](https://devblogs.microsoft.com/typescript/announcing-typescript-5-0/#speed-memory-and-package-size-optimizations). Shipglass 0.3.2 compared the exact published archives for [TypeScript 4.9.5](https://registry.npmjs.org/typescript/4.9.5) and [5.0.4](https://registry.npmjs.org/typescript/5.0.4) on October 3, 2026, without installing or executing either package.

## Reproduce

With Shipglass 0.3.0 or newer installed, run:

```sh
shipglass npm typescript 4.9.5 5.0.4 \
  --output typescript.html \
  --json typescript.json \
  --markdown typescript-summary.md
```

The command downloads the two archives from the official npm registry and checks their published integrity metadata. Open `typescript.html` locally; it is a self-contained report. See the [npm guide](../npm.md) for network behavior and limits.

## Observed result

| Measurement | 4.9.5 | 5.0.4 | Change |
| --- | ---: | ---: | ---: |
| Compressed archive bytes | 11,620,433 | 7,051,452 | −4,568,981 (−39.3%) |
| Expanded payload bytes | 66,849,652 | 39,203,145 | −27,646,507 (−41.4%) |
| Files | 108 | 107 | −1 |

Shipglass finds **6 added, 7 removed, 95 changed, and 6 unchanged** paths. The small change in file count hides a substantial change in contents.

| Path | Before bytes | After bytes | Change |
| --- | ---: | ---: | ---: |
| `package/lib/typescriptServices.js` | 10,945,736 | Removed | −10,945,736 |
| `package/lib/typingsInstaller.js` | 8,148,122 | 1,874,430 | −6,273,692 |
| `package/lib/tsserver.js` | 11,676,702 | 8,261,284 | −3,415,418 |
| `package/lib/tsserverlibrary.js` | 11,615,475 | 8,736,786 | −2,878,689 |
| `package/lib/typescript.js` | 10,945,729 | 8,113,774 | −2,831,955 |

The removal of `typescriptServices.js` alone accounts for **39.6% of the net payload reduction**. Microsoft's [migration to modules article](https://devblogs.microsoft.com/typescript/typescripts-migration-to-modules/#spring-cleaning) explains why this file, its declaration file, and `protocol.d.ts` were removed; the [implementation PR](https://github.com/microsoft/TypeScript/pull/51387) documents the underlying migration.

In the report, choose **Removed** to inspect those entries, or **Changed** and sort by **Largest change** to find the smaller compiler and server files. Switch to **Before** to see where the old release's bytes were concentrated.

These measurements describe the two npm archives. They do not measure compiler speed or application bundle size; consult TypeScript's release notes when assessing compatibility.
