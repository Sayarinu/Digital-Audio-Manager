"""One entry point for source installs and frozen desktop/worker processes."""

import sys


def process_command(mode):
    if getattr(sys, "frozen", False):
        return [sys.executable, "--" + mode]
    return [sys.executable, "-m", "dam", "--" + mode]


def main():
    if "--audio-smoke-test" in sys.argv:
        from .player import decoder_smoke_test
        return decoder_smoke_test()
    if "--extractor" in sys.argv:
        import yt_dlp
        yt_dlp.main(sys.argv[sys.argv.index("--extractor") + 1:])
        return 0
    if "--provider" in sys.argv:
        sys.stdin.reconfigure(encoding="utf-8")
        sys.stdout.reconfigure(encoding="utf-8")
        from .provider import main as run
    else:
        from .app import main as run
    return run()
