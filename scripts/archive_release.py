"""Archive a native app with executable modes and macOS framework symlinks intact."""

from pathlib import Path
import stat
import sys
import zipfile

from dam.updates.updates import APP_NAME, asset_name


def archive(version, directory=Path("dist"), output=Path(".")):
    root = directory / (APP_NAME + (".app" if sys.platform == "darwin" else ""))
    if not root.is_dir():
        raise ValueError("Native build is missing")
    target = output / asset_name(version)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(root.rglob("*")):
            name = path.relative_to(directory).as_posix()
            if path.is_symlink():
                info = zipfile.ZipInfo(name)
                info.create_system = 3
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
                bundle.writestr(info, str(path.readlink()))
            elif path.is_file():
                bundle.write(path, name)
    return target


if __name__ == "__main__":
    print(archive(sys.argv[1]))
