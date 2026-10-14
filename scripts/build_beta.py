"""Build a local onedir Beta using an explicit non-secret data allowlist."""
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from smart_tray.beta import VERSION

FILES = ["diagnostics/provisioned.json", "diagnostics/discovery-current.json",
    "profiles/elgin_profile.json", "profiles/led_profile.json", "profiles/novadigital_profile.json",
    "diagnostics/elgin-research/schema-current.json", "diagnostics/led-research/schema-current.json",
    "diagnostics/elgin-research/session-547a173fad8342aabf2dc08bbe848bcc.json",
    "diagnostics/elgin-research/session-ad51b3c964544e57a8449791c10eebcd.json",
    "diagnostics/elgin-integration.md", "diagnostics/beta-guide.md", "diagnostics/beta-responsiveness.md"]


def assert_no_credentials(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key.lower().replace("_", "") in {"localkey", "accesssecret", "accessid", "accesstoken", "refreshtoken", "password", "token"}:
                raise ValueError("Credential field forbidden in bundle data")
            assert_no_credentials(item)
    elif isinstance(value, list):
        for item in value:
            assert_no_credentials(item)


def main():
    staging = ROOT / "build/beta-data"
    for relative in FILES:
        source = ROOT / relative
        if source.suffix == ".json":
            assert_no_credentials(json.loads(source.read_text(encoding="utf-8")))
        target = staging / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    # Use the existing painted app icon; no external asset or arbitrary executable.
    from PySide6.QtWidgets import QApplication
    from smart_tray.ui import icon
    app = QApplication.instance() or QApplication([])
    icon_path = ROOT / "build/smart-tray.ico"
    if not icon(size=24).pixmap(256, 256).save(str(icon_path), "ICO"):
        raise RuntimeError("Icon generation failed")
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--onedir", "--windowed",
        "--name", "SmartTrayBeta", "--paths", str(ROOT / "src"), "--icon", str(icon_path),
        "--add-data", str(staging) + ";data", "--distpath", str(ROOT / "dist"),
        "--workpath", str(ROOT / "build/pyinstaller"), "--specpath", str(ROOT / "build"),
        "--exclude-module", "pytest", "--exclude-module", "PySide6.QtWebEngineCore",
        "--exclude-module", "PySide6.QtWebEngineWidgets", str(ROOT / "scripts/beta_entry.py")]
    subprocess.run(command, cwd=ROOT, check=True)
    manifest = {"version": VERSION, "format": "onedir", "data_files": FILES, "credentials_included": False}
    (ROOT / "dist/SmartTrayBeta/build-info.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("Local Beta built: dist/SmartTrayBeta/SmartTrayBeta.exe")


if __name__ == "__main__":
    main()
