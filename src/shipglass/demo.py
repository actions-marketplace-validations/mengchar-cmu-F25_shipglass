"""Build deterministic, synthetic release archives for the interactive demo."""
from __future__ import annotations

import gzip
import io
import tarfile
from pathlib import Path


def _sized(text: bytes, size: int) -> bytes:
    return (text * (size // len(text) + 1))[:size]


def _archive(path: Path, files: dict[str, bytes]) -> None:
    with path.open('wb') as raw, gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode='w') as archive:
            for name, content in sorted(files.items()):
                info = tarfile.TarInfo(name)
                info.size = len(content)
                info.mode = 0o644
                archive.addfile(info, io.BytesIO(content))


def create_demo(directory: Path) -> tuple[Path, Path]:
    """Create fixtures, containing no real credentials or third-party code."""
    before = {
        'package/package.json': b'{"name":"demo-orbit-ui","version":"1.4.0"}\n',
        'package/README.md': _sized(b'# Orbit UI demo\nSynthetic release fixture.\n', 16_384),
        'package/LICENSE': b'Synthetic demonstration data, dedicated to the public domain.\n',
        'package/dist/index.js': _sized(b'export const orbit = 1;\n', 384_000),
        'package/dist/vendor.js': _sized(b'// Synthetic vendor placeholder\n', 1_200_000),
        'package/dist/styles.css': _sized(b'.orbit { display: grid; }\n', 192_000),
        'package/assets/preview.svg': _sized(b'<!-- Synthetic illustration placeholder -->\n', 256_000),
        'package/types/index.d.ts': _sized(b'export declare const orbit: number;\n', 12_288),
        'package/docs/migration.md': _sized(b'Migrate the old orbit API.\n', 8192),
    }
    after = dict(before)
    after['package/package.json'] = b'{"name":"demo-orbit-ui","version":"1.4.1"}\n'
    after['package/dist/index.js'] = _sized(b'export const orbit = 2;\n', 384_512)
    after['package/dist/index.js.map'] = _sized(b'{"demo":"synthetic source map payload"}\n', 6 * 1024 * 1024)
    after['package/.env'] = b'SHIPGLASS_DEMO_ONLY=yes\n'
    after['package/private/deploy.key'] = b'NOT A REAL KEY. Synthetic filename-check fixture only.\n'
    after['package/.cache/build.bin'] = _sized(b'SYNTHETIC CACHE\n', 384_000)
    del after['package/docs/migration.md']
    directory.mkdir(parents=True, exist_ok=True)
    first, second = directory / 'orbit-ui-1.4.0.tgz', directory / 'orbit-ui-1.4.1.tgz'
    _archive(first, before)
    _archive(second, after)
    return first, second
