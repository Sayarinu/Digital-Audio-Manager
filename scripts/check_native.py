"""Exercise every native page at the supported bounds without accounts or networking."""

import os
import json
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    environment = dict(os.environ, QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software")
    command = sys.argv[1:] or [sys.executable, "-m", "dam"]
    with tempfile.TemporaryDirectory(prefix="dam-visual-") as directory:
        worker_environment = dict(environment, MP3_MAKER_APP_DATA=str(Path(directory) / "data"),
                                  MP3_MAKER_LIBRARY=str(Path(directory) / "music"))
        worker = subprocess.run([*command, "--provider"],
                                input=json.dumps({"id": 1, "operation": "initialize"}) + "\n",
                                env=worker_environment, capture_output=True, text=True, timeout=45)
        if worker.returncode or not json.loads(worker.stdout).get("ok"):
            print("Packaged library worker failed to initialize.", file=sys.stderr)
            return 1
        extractor = subprocess.run([*command, "--extractor", "--version"], env=environment,
                                   capture_output=True, text=True, timeout=45)
        if extractor.returncode or not extractor.stdout.strip():
            print("Bundled extractor failed to start.", file=sys.stderr)
            return 1
        for width, height in ((1280, 820), (920, 620), (1600, 900)):
            for view in ("library", "downloads", "queue", "device", "settings", "collection"):
                target = Path(directory) / f"{view}-{width}.png"
                result = subprocess.run([*command, "--smoke-test", "--view", view,
                                         "--width", str(width), "--height", str(height),
                                         "--screenshot", str(target)], env=environment,
                                        capture_output=True, text=True, timeout=45)
                if result.returncode or not target.is_file() or "file:" in result.stderr or "failed to load" in result.stderr:
                    print(f"Native check failed: {view} at {width}x{height}\n{result.stderr}", file=sys.stderr)
                    return 1
        for options in (["--dialog", "account"], ["--dialog", "import"], ["--empty"],
                        ["--empty", "--state", "loading"], ["--state", "error"]):
            target = Path(directory) / "dialog-state.png"
            result = subprocess.run([*command, "--smoke-test", "--width", "920", "--height", "620",
                                     "--screenshot", str(target), *options], env=environment,
                                    capture_output=True, text=True, timeout=45)
            if result.returncode or not target.is_file() or "file:" in result.stderr or "failed to load" in result.stderr:
                print(f"Native dialog/state check failed: {options}\n{result.stderr}", file=sys.stderr)
                return 1
        print("Native render checks passed: 6 views at 3 sizes, dialogs, loading, empty and error states.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
