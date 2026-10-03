# Rich: 13.9.4 → 14.0.0

[Open the interactive report](https://mengchar-cmu-f25.github.io/shipglass/?example=rich) for two real Python wheels, compared with Shipglass **0.2.0**. The wheels were downloaded from official PyPI release metadata: [Rich 13.9.4](https://pypi.org/pypi/rich/13.9.4/json) and [Rich 14.0.0](https://pypi.org/pypi/rich/14.0.0/json). Neither package was installed or executed.

| Measurement | 13.9.4 | 14.0.0 | Change |
| --- | ---: | ---: | ---: |
| Wheel archive | 242,424 B | 243,229 B | +805 B |
| Expanded file bytes | 955,765 B | 959,611 B | +3,846 B (+0.40%) |
| Files | 83 | 83 | 0 |

Shipglass finds **4 added, 4 removed, 7 changed, and 72 unchanged paths**. Zero current-release filename cautions were reported; filename checks are not a security audit.

The largest size increase at a matching path is `rich/traceback.py`: **31,725 → 35,098 B**, an increase of **3,373 B**. Next are `rich/console.py` (+409 B) and `rich/default_styles.py` (+98 B). These are packaging measurements; they do not establish a performance regression or explain the code's behavior.

The largest individual added and removed entries are each `METADATA` (18,274 B). All four added/removed pairs belong to `rich-13.9.4.dist-info/` and `rich-14.0.0.dist-info/`: `METADATA`, `RECORD`, `LICENSE`, and `WHEEL`. The [wheel specification](https://packaging.python.org/en/latest/specifications/binary-distribution-format/#file-contents) includes the version in this metadata directory's name. Shipglass compares exact member paths, so the changed directory name produces additions and removals. It does not infer renames or equate files merely because their sizes match. Each release's four metadata files total 25,435 B, contributing zero net growth.

## Reproduce

With Python 3.10+ and Shipglass 0.2.0 installed, run this in a shell. It creates a clean temporary folder, resolves the exact universal wheel filenames from the version-specific PyPI JSON, and downloads only those wheels.

```sh
rich_example_dir="$(mktemp -d)"
cd "$rich_example_dir"

python3 - <<'PY'
import json
from urllib.request import urlopen, urlretrieve

for version in ("13.9.4", "14.0.0"):
    with urlopen(f"https://pypi.org/pypi/rich/{version}/json") as response:
        release = json.load(response)
    filename = f"rich-{version}-py3-none-any.whl"
    wheel = next(
        file for file in release["urls"]
        if file["filename"] == filename and file["packagetype"] == "bdist_wheel"
    )
    urlretrieve(wheel["url"], filename)
    print(filename)
PY

shipglass --version
shipglass compare \
  rich-13.9.4-py3-none-any.whl \
  rich-14.0.0-py3-none-any.whl \
  --output rich.html \
  --json rich.json \
  --markdown rich-summary.md
```

Open `rich.html` locally. Search for `rich/traceback.py`, switch between Before and After, or choose the Added filter to inspect the versioned metadata. The report is self-contained and contains file metadata, not the wheels' source contents.
