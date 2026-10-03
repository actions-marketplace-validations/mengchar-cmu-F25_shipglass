"""Download exact public npm releases without installing or extracting them."""

from __future__ import annotations

import base64
import binascii
import hashlib
import http.client
import json
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from . import core

MAX_METADATA_BYTES = 1024 * 1024
NETWORK_TIMEOUT = 30
_NAME = re.compile(r"(?:@[A-Za-z0-9][A-Za-z0-9._-]*/)?[A-Za-z0-9][A-Za-z0-9._-]*")
_NUMBER = r"(?:0|[1-9][0-9]*)"
_PRERELEASE = r"(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)"
_VERSION = re.compile(rf"{_NUMBER}\.{_NUMBER}\.{_NUMBER}(?:-{_PRERELEASE}(?:\.{_PRERELEASE})*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?")


def _registry_url(url: str) -> None:
    if not isinstance(url, str) or any(char.isspace() or ord(char) < 32 or ord(char) == 127 or char == "\\" for char in url):
        raise ValueError("Invalid npm registry URL")
    parts = urllib.parse.urlsplit(url)
    if (parts.scheme != "https" or parts.hostname != "registry.npmjs.org"
            or parts.port not in (None, 443) or parts.username is not None
            or parts.password is not None or parts.fragment):
        raise ValueError("npm downloads require HTTPS registry.npmjs.org URLs")


class _RegistryRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _registry_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _chunks(response, limit: int, label: str):
    declared = response.headers.get("Content-Length")
    if declared is not None:
        if not re.fullmatch(r"[0-9]+", declared):
            raise ValueError("Invalid npm response length")
        declared = int(declared)
        if declared > limit:
            raise ValueError(f"npm {label} exceeds the {limit:,}-byte limit")
    total = 0
    while True:
        chunk = response.read(min(core.CHUNK_BYTES, limit - total + 1))
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise ValueError(f"npm {label} exceeds the {limit:,}-byte limit")
        yield chunk
    if declared is not None and total != declared:
        raise ValueError(f"npm {label} has an inconsistent response length")


def _published_digest(dist: dict) -> tuple[str, set[bytes]]:
    if "integrity" in dist:
        integrity = dist["integrity"]
        if not isinstance(integrity, str) or not integrity.strip():
            raise ValueError("Invalid npm integrity metadata")
        digests: dict[str, set[bytes]] = {}
        for token in integrity.split():
            algorithm, _, encoded = token.partition("-")
            if algorithm not in ("sha512", "sha384", "sha256", "sha1"):
                raise ValueError("Unsupported npm integrity digest")
            try:
                digest = base64.b64decode(encoded.split("?", 1)[0], validate=True)
            except (ValueError, binascii.Error) as error:
                raise ValueError("Invalid npm integrity metadata") from error
            if len(digest) != hashlib.new(algorithm).digest_size:
                raise ValueError("Invalid npm integrity metadata")
            digests.setdefault(algorithm, set()).add(digest)
        for algorithm in ("sha512", "sha384", "sha256", "sha1"):
            if algorithm in digests:
                return algorithm, digests[algorithm]
    shasum = dist.get("shasum")
    if not isinstance(shasum, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", shasum):
        raise ValueError("npm metadata is missing a valid archive digest")
    return "sha1", {bytes.fromhex(shasum)}


def download(package: str, version: str, directory: Path) -> Path:
    """Fetch and verify an exact public release, leaving no file on failure."""
    if not isinstance(package, str) or len(package) > 214 or not _NAME.fullmatch(package):
        raise ValueError("Use a public npm package name, such as lodash or @scope/name")
    if not isinstance(version, str) or len(version) > 256 or not _VERSION.fullmatch(version):
        raise ValueError("Use an exact npm version, such as 1.2.3; tags and ranges are unsupported")
    url = f"https://registry.npmjs.org/{urllib.parse.quote(package, safe='')}/{urllib.parse.quote(version, safe='')}"
    opener = urllib.request.build_opener(_RegistryRedirect())
    path = None
    complete = False
    try:
        request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "shipglass"})
        with opener.open(request, timeout=NETWORK_TIMEOUT) as response:
            _registry_url(response.geturl())
            raw = b"".join(_chunks(response, MAX_METADATA_BYTES, "metadata"))
        try:
            metadata = json.loads(raw)
        except (ValueError, UnicodeError, RecursionError) as error:
            raise ValueError("Invalid npm version metadata") from error
        if not isinstance(metadata, dict):
            raise ValueError("Invalid npm version metadata")
        if metadata.get("name") != package or metadata.get("version") != version:
            raise ValueError("npm metadata does not match the requested package and version")
        dist = metadata.get("dist")
        if not isinstance(dist, dict):
            raise ValueError("npm metadata is missing archive details")
        tarball = dist.get("tarball")
        _registry_url(tarball)
        algorithm, expected = _published_digest(dist)
        digest = hashlib.new(algorithm)
        request = urllib.request.Request(tarball, headers={"User-Agent": "shipglass"})
        with opener.open(request, timeout=NETWORK_TIMEOUT) as response:
            _registry_url(response.geturl())
            prefix = f"{package.lstrip('@').replace('/', '-')[:80]}-{version[:80]}-"
            with tempfile.NamedTemporaryFile(prefix=prefix, suffix=".tgz", dir=directory, delete=False) as target:
                path = Path(target.name)
                for chunk in _chunks(response, core.MAX_ARCHIVE_BYTES, "archive"):
                    target.write(chunk)
                    digest.update(chunk)
        if digest.digest() not in expected:
            raise ValueError("npm archive digest does not match the published metadata")
        complete = True
        return path
    except urllib.error.HTTPError as error:
        if error.code == 404:
            raise ValueError(f"npm package or version was not found: {package}@{version}") from error
        raise OSError(f"npm registry request failed (HTTP {error.code})") from error
    except (urllib.error.URLError, http.client.HTTPException, TimeoutError) as error:
        raise OSError("Cannot download from the public npm registry") from error
    finally:
        if path is not None and not complete:
            path.unlink(missing_ok=True)
