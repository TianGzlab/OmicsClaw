"""Build tiny wheels and sdists in a test's temporary directory, so installation tests need no network.

The approach of plan 0061 appendix A (``mkwheel.py``): a wheel is a zip with
``METADATA``, ``WHEEL`` and a ``RECORD`` whose hashes are right, and pip
installs it like any other. Nothing here touches the repository.
"""

from __future__ import annotations

import base64
import hashlib
import io
import tarfile
import zipfile
from collections.abc import Iterable, Mapping
from pathlib import Path


def make_wheel(
    directory: Path,
    name: str,
    version: str,
    *,
    requires: Iterable[str] = (),
    files: Mapping[str, str] | None = None,
    build: int | None = None,
) -> Path:
    """Write ``<name>-<version>[-<build>]-py3-none-any.whl`` into *directory* and return its path.

    *files* maps paths inside the wheel to their text; the default is one
    module named after the project, defining ``VALUE``.
    """
    directory.mkdir(parents=True, exist_ok=True)
    stem = name.replace("-", "_")
    content = dict(files) if files is not None else {f"{stem}.py": f"VALUE = {version!r}\n"}
    info = f"{stem}-{version}.dist-info"
    content[f"{info}/METADATA"] = (
        f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n"
        + "".join(f"Requires-Dist: {requirement}\n" for requirement in requires)
    )
    content[f"{info}/WHEEL"] = (
        "Wheel-Version: 1.0\nGenerator: omicsclaw-tests\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
        + (f"Build: {build}\n" if build is not None else "")
    )
    record = []
    for path, text in content.items():
        data = text.encode()
        digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
        record.append(f"{path},sha256={digest},{len(data)}")
    record.append(f"{info}/RECORD,,")
    content[f"{info}/RECORD"] = "\n".join(record) + "\n"
    filename = f"{stem}-{version}" + (f"-{build}" if build is not None else "") + "-py3-none-any.whl"
    target = directory / filename
    with zipfile.ZipFile(target, "w") as archive:
        for path, text in content.items():
            archive.writestr(path, text)
    return target


def make_sdist(directory: Path, name: str, version: str, *, setup_code: str = "") -> Path:
    """Write ``<name>-<version>.tar.gz`` with a ``setup.py`` that runs *setup_code* first."""
    directory.mkdir(parents=True, exist_ok=True)
    stem = f"{name.replace('-', '_')}-{version}"
    files = {
        f"{stem}/setup.py": f"{setup_code}\nfrom setuptools import setup\nsetup(name={name!r}, version={version!r})\n",
        f"{stem}/PKG-INFO": f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n",
    }
    target = directory / f"{stem}.tar.gz"
    with tarfile.open(target, "w:gz") as archive:
        for path, text in files.items():
            data = text.encode()
            member = tarfile.TarInfo(path)
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
    return target


def pip_conf(path: Path, *, find_links: Iterable[Path | str] = (), no_index: bool = True, extra: str = "") -> Path:
    """Write a pip configuration file for offline installation from *find_links*."""
    lines = ["[global]"]
    if no_index:
        lines.append("no-index = true")
    links = [str(item) for item in find_links]
    if links:
        lines.append("find-links =")
        lines.extend(f"    {link}" for link in links)
    text = "\n".join(lines) + "\n" + extra
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path
