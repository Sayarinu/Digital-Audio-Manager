"""Run the GUI checks in their own process, separate from QCoreApplication tests."""

from pathlib import Path
import subprocess
import sys


def test_native_dialogs_navigation_and_scroll_preservation():
    script = Path(__file__).parents[1] / "scripts" / "check_interactions.py"
    result = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, timeout=45)
    assert result.returncode == 0, result.stdout + result.stderr
    assert '"scroll_preserved": true' in result.stdout
