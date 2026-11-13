import base64
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time
import zipfile

from Cryptodome.Signature import eddsa
import pytest

from dam.updates import maintenance, package_signature, updates


@pytest.mark.parametrize('version,tag', [
    ('1.2.3', 'Digital-Audio-Manager-1.2.3'),
    ('1.2.4b2', 'Digital-Audio-Manager-Experimental-1.2.4b2'),
])
def test_channel_tags_round_trip(version, tag):
    assert updates.release_tag(version) == tag
    assert updates.tag_version(tag) == version
    assert updates.version_key(tag) == updates.version_key(version)
    assert updates.version_key('1.2.3') < updates.version_key('1.2.4b2') < updates.version_key('1.2.4')
    assert updates.tag_version('v1.0.1') is None
    assert updates.tag_version('Digital-Audio-Manager-1.2.4b2') is None


def test_channel_lookup_ignores_drafts_and_mislabeled_prereleases():
    rows = [dict(tag_name=updates.release_tag('1.2.3'), prerelease=False),
            dict(tag_name=updates.release_tag('1.2.4b1'), prerelease=True),
            dict(tag_name=updates.release_tag('9.0.0'), prerelease=False, draft=True),
            dict(tag_name=updates.release_tag('8.0.0'), prerelease=True)]
    def opener(*args, **kwargs):
        return io.BytesIO(json.dumps(rows).encode())
    assert maintenance.lookup_release(opener, 'stable')['tag'] == updates.release_tag('1.2.3')
    assert maintenance.lookup_release(opener, 'experimental')['tag'] == updates.release_tag('1.2.4b1')


def test_asset_selection_requires_exact_platform_and_signature():
    version = '1.2.4b1'
    name = updates.asset_name(version, 'win32', 'AMD64')
    asset = dict(name=name, size=123, digest='sha256:' + 'a' * 64)
    release = dict(tag_name=updates.release_tag(version), assets=[asset])
    with pytest.raises(updates.UnsignedUpdate):
        updates.select_asset(release, 'win32', 'AMD64')
    release['assets'].append(dict(asset, name=name + '.sig'))
    assert updates.select_asset(release, 'win32', 'AMD64')['name'] == name
    with pytest.raises(updates.UnsignedUpdate):
        updates.select_asset(release, 'darwin', 'arm64')


def test_download_size_and_digest_are_checked(tmp_path):
    asset = dict(name='test.zip', size=4, sha256=hashlib.sha256(b'good').hexdigest())
    progress = []
    path = updates.fetch('tag', asset, tmp_path, progress.append, lambda *a, **k: io.BytesIO(b'good'))
    assert path.read_bytes() == b'good'
    assert progress[-1]['percent'] == 100
    for data in [b'evil', b'too large']:
        with pytest.raises(ValueError):
            updates.fetch('tag', asset, tmp_path, None, lambda *a, **k: io.BytesIO(data))
        assert not list(tmp_path.glob('*.part'))


def zip_bytes(entries):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as bundle:
        for name, value in entries:
            if isinstance(name, str):
                info = zipfile.ZipInfo()
                info.filename = info.orig_filename = name
                name = info
            bundle.writestr(name, value)
    stream.seek(0)
    return stream


@pytest.mark.parametrize('name', ['../outside', '/outside', 'App/../outside', 'Other/file', 'App/file:stream', 'App/dir\\file'])
def test_extraction_refuses_paths_outside_the_app(tmp_path, name):
    with pytest.raises(ValueError):
        updates.unpack(zip_bytes([(name, b'bad')]), tmp_path, 'App')
    assert not (tmp_path.parent / 'outside').exists()


def test_framework_links_are_confined_and_created_last(tmp_path):
    link = zipfile.ZipInfo('App/framework/Current')
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    package = zip_bytes([(link, b'A'), ('App/framework/A/binary', b'framework')])
    if sys.platform == 'win32':
        with pytest.raises(ValueError):
            updates.unpack(package, tmp_path, 'App')
    else:
        updates.unpack(package, tmp_path, 'App')
        assert (tmp_path / 'App/framework/Current/binary').read_bytes() == b'framework'
    package = zip_bytes([(link, b'../../../outside')])
    with pytest.raises(ValueError):
        updates.unpack(package, tmp_path / 'unsafe', 'App')


def signed_archive(tmp_path, monkeypatch):
    monkeypatch.setenv("MP3_MAKER_APP_DATA", str(tmp_path / "data"))
    monkeypatch.setenv("MP3_MAKER_LIBRARY", str(tmp_path / "music"))
    root = tmp_path / updates.APP_NAME
    root.mkdir()
    executable = root / 'app'
    executable.write_bytes(b'old executable')
    monkeypatch.setattr(updates, 'installed_root', lambda: root)
    monkeypatch.setattr(sys, 'executable', str(executable))
    seed = b'1' * 32
    public = eddsa.import_private_key(seed).public_key().export_key(format='raw')
    key = tmp_path / 'public-key'
    key.write_bytes(base64.b64encode(public))
    monkeypatch.setattr(updates, 'update_public_key', lambda: key)
    package = tmp_path / 'update.zip'
    package.write_bytes(zip_bytes([(root.name + '/app', b'new executable')]).getvalue())
    signature = tmp_path / 'update.zip.sig'
    signature.write_text(package_signature.sign(package.read_bytes(), base64.b64encode(seed + public).decode()))
    return root, dict(path=str(package), signature_path=str(signature), sha256=hashlib.sha256(package.read_bytes()).hexdigest())


def test_staging_verifies_signature_before_touching_install(tmp_path, monkeypatch):
    root, asset = signed_archive(tmp_path, monkeypatch)
    plan = updates.prepare_install(asset)
    assert (root / 'app').read_bytes() == b'old executable'
    assert (Path(plan['staged']) / root.name / 'app').read_bytes() == b'new executable'
    Path(asset['signature_path']).write_text(base64.b64encode(b'0' * 64).decode())
    with pytest.raises(updates.UnsignedUpdate):
        updates.prepare_install(asset)
    assert (root / 'app').read_bytes() == b'old executable'


@pytest.mark.parametrize('failure', [False, True], ids=['replace', 'rollback'])
def test_installer_waits_swaps_or_rolls_back_and_restarts(tmp_path, failure):
    root = tmp_path / 'App With Spaces'
    root.mkdir()
    stage = tmp_path / '.dam-update-test'
    stage.mkdir()
    new = stage / root.name
    new.mkdir()
    output = tmp_path / 'restarted.txt'
    entry = 'app.cmd' if os.name == 'nt' else 'app.sh'
    for directory, label in [(root, 'old'), (new, 'new')]:
        text = (f'@echo {label}>"{output}"\r\n' if os.name == 'nt'
                else f'#!/bin/sh\nprintf "{label}" > "{output}"\n')
        (directory / entry).write_text(text)
        (directory / entry).chmod(0o755)
    (tmp_path / 'library.sqlite3').write_bytes(b'keep library')
    parent = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(.4)'])
    script = stage / ('apply.ps1' if os.name == 'nt' else 'apply.sh')
    script.write_text(updates.WINDOWS_INSTALL if os.name == 'nt' else updates.POSIX_INSTALL)
    receipt = tmp_path / 'result.json'
    if failure:
        new.rename(stage / 'missing')
    command = (['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File']
               if os.name == 'nt' else ['/bin/sh'])
    installer = subprocess.Popen([*command, str(script), str(parent.pid), str(root), str(stage), entry, str(receipt)],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert not receipt.exists()
    parent.wait(timeout=5)
    stdout, stderr = installer.communicate(timeout=15)
    assert installer.returncode == 0, stdout + stderr
    for _ in range(100):
        if output.exists():
            break
        time.sleep(.03)
    assert json.loads(receipt.read_text())['success'] is not failure
    assert output.read_text().strip() == ('old' if failure else 'new')
    assert (tmp_path / 'library.sqlite3').read_bytes() == b'keep library'
    assert not stage.exists()


def test_switch_to_older_stable_requires_fresh_confirmation(tmp_path, monkeypatch):
    from PySide6.QtCore import QCoreApplication, QObject, QSettings, Signal

    class FakeWorker(QObject):
        succeeded = Signal(int, dict)
        failed = Signal(int, dict)
        progress = Signal(int, dict)

        def __init__(self, *args, **kwargs):
            super().__init__()
            self.requests = []

        def request(self, operation, payload):
            self.requests.append(payload)
            return len(self.requests)

        def close(self):
            pass

    class Shell:
        busy = ''
        queueRunning = False
        settings = QSettings(str(tmp_path / 'settings.ini'), QSettings.Format.IniFormat)

    _app = QCoreApplication.instance() or QCoreApplication([])
    monkeypatch.setattr(maintenance, 'installed_version', lambda: '1.2.4b3')
    monkeypatch.setattr(updates, 'supported', lambda: True)
    controller = maintenance.Maintenance(tmp_path / 'release.json', Shell(), worker_factory=FakeWorker)
    assert controller.channel == 'experimental'
    controller.setChannel('stable')
    result = {'tag': updates.release_tag('1.2.3')}
    controller._worker.succeeded.emit(1, result)
    assert controller.updateAvailable and controller.downgrading and controller.switchingChannel
    controller.installUpdate()
    assert controller._worker.requests[-1]['action'] == 'release'
    controller._worker.succeeded.emit(2, dict(result, stale=True))
    assert all(row['action'] != 'download' for row in controller._worker.requests)
    controller.installUpdate()
    controller._worker.succeeded.emit(3, result)
    assert controller._worker.requests[-1]['action'] == 'download'
    controller.close()


def test_release_version_counts_experimental_builds_and_promotes_stable(monkeypatch):
    import importlib.util

    spec = importlib.util.spec_from_file_location('release_version', Path(__file__).parents[1] / 'scripts/release_version.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, 'declared', lambda: (1, 0, 1))
    monkeypatch.setattr(module, 'newest_stable_tag', lambda: ((1, 2, 0), updates.release_tag('1.2.0')))
    monkeypatch.setattr(module, 'experimental_builds', lambda version: [1, 2])
    monkeypatch.setattr(module, 'previous_experimental', lambda: updates.release_tag('1.3.0b2'))
    monkeypatch.setattr(module, 'git', lambda *args: 'commit')
    result = module.release_version({'GITHUB_REF': 'refs/heads/experimental', 'GITHUB_EVENT_NAME': 'push'}, labels=lambda sha: {'Feature'})
    assert result[:2] == ('1.3.0b3', 'feature')
    monkeypatch.setattr(module, 'previous_tag', lambda: updates.release_tag('1.2.0'))
    result = module.release_version({'GITHUB_REF': 'refs/heads/main', 'GITHUB_EVENT_NAME': 'push'}, labels=lambda sha: {'Feature'})
    assert result[:2] == ('1.3.0', 'feature')
