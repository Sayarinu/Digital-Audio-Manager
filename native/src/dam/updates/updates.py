"""Signed native bundles and a detached, rollback-capable portable installer."""

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import stat
import sys
import tempfile
from urllib.request import Request, urlopen
import zipfile

BASE = "https://github.com/Sayarinu/Digital-Audio-Manager/releases/download/"
API = "https://api.github.com/repos/Sayarinu/Digital-Audio-Manager/releases/tags/"
APP_NAME = "Digital Audio Manager"
MAX_DOWNLOAD = 1024 * 1024 * 1024
MAX_SIGNATURE = 4096
VERSION = re.compile(r"(\d+)\.(\d+)\.(\d+)(?:b(\d+))?")
STABLE_TAG = re.compile(r"Digital-Audio-Manager-(\d+\.\d+\.\d+)")
EXPERIMENTAL_TAG = re.compile(r"Digital-Audio-Manager-Experimental-(\d+\.\d+\.\d+b\d+)")

def tag_version(tag):
    """The version a release tag names, or None. Digital Audio Manager- tags must agree with the version's channel."""
    if not isinstance(tag, str):
        return None
    for pattern in (STABLE_TAG, EXPERIMENTAL_TAG):
        match = pattern.fullmatch(tag)
        if match:
            return match.group(1)
    return None


def version_key(value):
    """Sortable (X, Y, Z, stable?, N): 0.7.0 < 0.7.1b1 < 0.7.1b2 < 0.7.1; None if invalid. Accepts versions and tags."""
    if not isinstance(value, str):
        return None
    match = VERSION.fullmatch(tag_version(value) or value)
    if not match:
        return None
    major, minor, patch, build = match.groups()
    return (int(major), int(minor), int(patch), 0 if build else 1, int(build or 0))


def is_experimental(value):
    key = version_key(value)
    return bool(key and key[3] == 0)


def release_tag(version):
    """The tag a version is released under; the one rule shared by CI and the app."""
    key = version_key(version)
    if not key or tag_version(version):
        raise ValueError('Invalid Digital Audio Manager version: ' + str(version))
    return ('Digital-Audio-Manager-Experimental-' if key[3] == 0 else 'Digital-Audio-Manager-') + version


def release_name(value):
    """What people see: "Digital Audio Manager 0.7.0" for stable builds, "Digital Audio Manager Experimental 0.7.1b3" for experimental ones."""
    key = version_key(value)
    if not key:
        return 'Digital Audio Manager'
    version = tag_version(value) or value
    return ('Digital Audio Manager Experimental ' if key[3] == 0 else 'Digital Audio Manager ') + version


class UnsignedUpdate(ValueError):
    """The release has no signature, or the download doesn't match it. Nothing gets installed."""


def integrity(item, limit):
    digest, size = item.get('digest', ''), item.get('size', 0)
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', digest) or type(size) is not int or not 0 < size <= limit:
        raise ValueError('Release is missing integrity metadata')
    return {'name': item['name'], 'sha256': digest[7:], 'size': size}



def atomic_write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".write-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(text)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def platform_key(system=None, machine=None):
    system, machine = system or sys.platform, (machine or platform.machine()).lower()
    systems = {"win32": "Windows", "darwin": "macOS", "linux": "Linux"}
    machines = {"amd64": "X64", "x86_64": "X64", "arm64": "ARM64", "aarch64": "ARM64"}
    if system not in systems or machine not in machines:
        raise ValueError("Unsupported update platform")
    return systems[system] + "-" + machines[machine]


def asset_name(version, system=None, machine=None):
    if not VERSION.fullmatch(version):
        raise ValueError("Invalid release version")
    return "Digital-Audio-Manager-" + version + "-" + platform_key(system, machine) + ".zip"


def select_asset(release, system=None, machine=None):
    tag = release.get("tag_name", "")
    version = tag_version(tag)
    if not version:
        raise ValueError("Invalid release")
    name = asset_name(version, system, machine)
    assets = release.get("assets", [])
    matches = [item for item in assets if item.get("name") == name]
    signatures = [item for item in assets if item.get("name") == name + ".sig"]
    if len(matches) != 1 or len(signatures) != 1:
        raise UnsignedUpdate("Release has no unique signed package for this platform")
    return {"tag": tag, **integrity(matches[0], MAX_DOWNLOAD), "signature": integrity(signatures[0], MAX_SIGNATURE)}


def installed_root():
    executable = Path(sys.executable).resolve()
    root = executable.parents[2] if sys.platform == "darwin" else executable.parent
    expected = APP_NAME + (".app" if sys.platform == "darwin" else "")
    if not getattr(sys, "frozen", False) or root.name != expected:
        raise ValueError("Only packaged app installations can update in place")
    return root


def supported():
    try:
        platform_key()
        root = installed_root()
        return os.access(root.parent, os.W_OK) and update_public_key().is_file()
    except (ValueError, OSError):
        return False


def update_public_key():
    return Path(__file__).resolve().parents[1] / "assets" / "update-public-key"


def check_signature(data, asset):
    from .package_signature import verify

    try:
        signature = Path(asset["signature_path"]).read_text(encoding="ascii")
        public = update_public_key().read_text(encoding="ascii")
    except (OSError, KeyError):
        raise UnsignedUpdate("Missing update signature or trust key") from None
    if not verify(data, signature, public):
        raise UnsignedUpdate("Update signature does not match")

def download(tag, directory, progress=None, opener=urlopen):
    """Re-fetch release metadata so an offline cache can never authorize execution."""
    if not tag_version(tag):
        raise ValueError('Invalid Digital Audio Manager release')
    request = Request(API + tag,
                      headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'Digital-Audio-Manager-updater'})
    with opener(request, timeout=15) as response:
        raw = response.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        raise ValueError('Release response too large')
    release = json.loads(raw)
    # Experimental tags must be published as prereleases and stable tags must not be.
    if release.get('draft') or bool(release.get('prerelease')) != is_experimental(tag) or release.get('tag_name') != tag:
        raise ValueError('Release unavailable')
    asset = select_asset(release)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = fetch(tag, asset, directory, progress, opener)
    result = {**asset, 'path': str(target)}
    if 'signature' in asset:
        try:
            result['signature_path'] = str(fetch(tag, asset['signature'], directory, None, opener))
        except BaseException:
            target.unlink(missing_ok=True)
            raise
    return result


def fetch(tag, asset, directory, progress, opener):
    target = directory / asset['name']
    partial = target.with_suffix(target.suffix + '.part')
    digest, count = hashlib.sha256(), 0
    try:
        with opener(BASE + tag + '/' + asset['name'], timeout=30) as response, partial.open('wb') as out:
            while chunk := response.read(256 * 1024):
                count += len(chunk)
                if count > asset['size']:
                    raise ValueError('Download exceeded expected size')
                out.write(chunk)
                digest.update(chunk)
                if progress:
                    progress({'percent': int(100 * count / asset['size'])})
        if count != asset['size'] or digest.hexdigest() != asset['sha256']:
            raise ValueError('Download integrity check failed')
        partial.replace(target)
        return target
    finally:
        partial.unlink(missing_ok=True)


def unpack(package, destination, root_name):
    """Extract only this app; create confined symlinks after all regular files."""
    destination = Path(destination)
    links, seen, total = [], set(), 0
    with zipfile.ZipFile(package) as archive:
        members = archive.infolist()
        if len(members) > 30000:
            raise ValueError("Update has too many files")
        for member in members:
            # ZipInfo normalizes backslashes on Windows; validate the original archive name.
            name = member.orig_filename.rstrip("/")
            parts = name.split("/")
            if (not name or parts[0] != root_name or any(p in {"", ".", ".."} for p in parts)
                    or "\\" in name or ":" in name or name in seen):
                raise ValueError("Unsafe or duplicate update path")
            seen.add(name)
            total += member.file_size
            if total > 2 * MAX_DOWNLOAD:
                raise ValueError("Expanded update is too large")
            target = destination.joinpath(*parts)
            mode = member.external_attr >> 16
            if stat.S_ISLNK(mode):
                link = archive.read(member).decode("utf-8")
                if sys.platform == "win32" or "\\" in link or PurePosixPath(link).is_absolute():
                    raise ValueError("Unsafe update link")
                resolved = (target.parent / link).resolve()
                if not resolved.is_relative_to(destination / root_name) or target == destination / root_name:
                    raise ValueError("Update link escapes the app")
                links.append((target, link))
            elif member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            elif stat.S_IFMT(mode) not in {0, stat.S_IFREG}:
                raise ValueError("Unsupported update file type")
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, target.open("xb") as output:
                    shutil.copyfileobj(source, output)
                target.chmod(0o755 if mode & 0o111 else 0o644)
        for target, link in links:
            target.parent.mkdir(parents=True, exist_ok=True)
            # No symlink may replace a parent already used by an extracted file.
            if target.exists() or target.is_symlink():
                raise ValueError("Conflicting update link")
            target.symlink_to(link)
        for target, _ in links:
            if not target.resolve().is_relative_to(destination / root_name):
                raise ValueError("Update link chain escapes the app")


def protect_user_data(root):
    from ..engine import connect, library_root
    from ..paths import data_directory

    if any(path.resolve().is_relative_to(root) for path in (data_directory(), library_root())):
        raise ValueError("Move app data and music outside the application folder before updating")
    con = connect()
    try:
        if any(Path(row[0]).resolve().is_relative_to(root)
               for row in con.execute("SELECT media_path FROM track WHERE media_path IS NOT NULL")):
            raise ValueError("Move downloaded music outside the application folder before updating")
    finally:
        con.close()


def prepare_install(asset):
    root = installed_root()
    protect_user_data(root)
    package = Path(asset["path"])
    data = package.read_bytes()
    if len(data) > MAX_DOWNLOAD or hashlib.sha256(data).hexdigest() != asset["sha256"]:
        raise ValueError("Update integrity check failed")
    check_signature(data, asset)
    stage = Path(tempfile.mkdtemp(prefix=".dam-update-", dir=root.parent))
    try:
        # Verify and extract the same bytes; replacing the cached archive cannot change the staged app.
        import io
        unpack(io.BytesIO(data), stage, root.name)
        entry = Path(sys.executable).resolve().relative_to(root)
        if not (stage / root.name / entry).is_file():
            raise ValueError("Update does not contain the app executable")
        script = stage / ("apply.ps1" if sys.platform == "win32" else "apply.sh")
        script.write_text(WINDOWS_INSTALL if sys.platform == "win32" else POSIX_INSTALL, encoding="utf-8")
        receipt = package.parent / "result.json"
        return {"staged": str(stage), "root": str(root), "entry": entry.as_posix(), "receipt": str(receipt)}
    except BaseException:
        shutil.rmtree(stage)
        raise


def launch_installer(result, parent_pid):
    from PySide6.QtCore import QProcess

    root = installed_root()
    stage = Path(result["staged"])
    if (Path(result["root"]) != root or stage.parent != root.parent or not stage.name.startswith(".dam-update-")
            or Path(result["entry"]) != Path(sys.executable).resolve().relative_to(root)
            or type(parent_pid) is not int or parent_pid <= 0):
        raise ValueError("Invalid installer plan")
    args = [str(parent_pid), str(root), str(stage), result["entry"], result["receipt"]]
    if sys.platform == "win32":
        program = str(Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe")
        args = ["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(stage / "apply.ps1"), *args]
    else:
        program = "/bin/sh"
        args = [str(stage / "apply.sh"), *args]
    # Start from the GUI, outside the worker process tree that shutdown terminates.
    started, _ = QProcess.startDetached(program, args)
    return started


POSIX_INSTALL = r'''#!/bin/sh
set -eu
parent="$1"; target="$2"; stage="$3"; entry="$4"; receipt="$5"
backup="$stage/previous"
new="$stage/${target##*/}"
n=0
while kill -0 "$parent" 2>/dev/null; do
    n=$((n + 1))
    if [ "$n" -ge 240 ]; then exit 1; fi
    sleep 0.25
done
success=false
if mv "$target" "$backup"; then
    if mv "$new" "$target"; then
        success=true
    else
        mv "$backup" "$target"
    fi
fi
printf '{"success":%s}\n' "$success" > "$receipt"
"$target/$entry" >/dev/null 2>&1 &
if [ "$success" = true ]; then rm -rf "$backup"; fi
rm -rf "$stage"
'''

WINDOWS_INSTALL = r'''param([int]$ParentProcess, [string]$Target, [string]$Stage, [string]$Entry, [string]$Receipt)
$ErrorActionPreference = 'Stop'
$backup = Join-Path $Stage 'previous'
$new = Join-Path $Stage (Split-Path $Target -Leaf)
for ($attempt = 0; $attempt -lt 240; $attempt++) {
    if (!(Get-Process -Id $ParentProcess -ErrorAction SilentlyContinue)) { break }
    Start-Sleep -Milliseconds 250
}
if (Get-Process -Id $ParentProcess -ErrorAction SilentlyContinue) { exit 1 }
$success = $false
try {
    Move-Item -LiteralPath $Target -Destination $backup
    try {
        Move-Item -LiteralPath $new -Destination $Target
        $success = $true
    } catch {
        Move-Item -LiteralPath $backup -Destination $Target
    }
} finally {
    @{success=$success} | ConvertTo-Json | Set-Content -LiteralPath $Receipt -Encoding Ascii
    Start-Process -FilePath (Join-Path $Target $Entry) -WorkingDirectory $Target
    if ($success) { Remove-Item -LiteralPath $backup -Recurse -Force }
    Remove-Item -LiteralPath $Stage -Recurse -Force
}
'''
