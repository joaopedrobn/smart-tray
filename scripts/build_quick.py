"""Local Qt Quick onedir build, using the existing non-secret data allowlist."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import argparse
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from smart_tray.beta import VERSION
from build_beta import FILES, assert_no_credentials


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path, help='Optional private profiles; never use for a public release')
    parser.add_argument('--distpath', type=Path, default=ROOT/'dist/public')
    args = parser.parse_args()
    (ROOT/'build').mkdir(exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='public-data-', dir=ROOT/'build'))
    files = [relative for relative in FILES if relative.endswith('.json')] if args.data_root else []
    for relative in files:
        source = args.data_root / relative
        if source.suffix == '.json':
            assert_no_credentials(json.loads(source.read_text(encoding='utf-8')))
        target = staging / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    if not args.data_root:
        for directory in ('diagnostics', 'profiles'):
            (staging/directory).mkdir(exist_ok=True)
        (staging/'diagnostics/provisioned.json').write_text('{"devices": []}', encoding='utf-8')
        (staging/'diagnostics/discovery-current.json').write_text('{"devices": []}', encoding='utf-8')
    from PySide6.QtWidgets import QApplication
    from smart_tray.ui import icon
    app = QApplication.instance() or QApplication([])
    icon_path = ROOT / 'build/smart-tray-2.ico'
    if not icon(size=24).pixmap(256, 256).save(str(icon_path), 'ICO'):
        raise RuntimeError('Icon generation failed')
    qml_staging = ROOT / 'build/production-qml'
    qml_staging.mkdir(parents=True, exist_ok=True)
    qml_files = [p for p in (ROOT / 'src/smart_tray/qml').glob('*.qml') if p.name != 'SceneDiscovery.qml']
    obsolete = qml_staging / 'SceneDiscovery.qml'
    if obsolete.exists():
        obsolete.unlink()  # Generated staging file only; source research is preserved.
    for source in qml_files:
        shutil.copy2(source, qml_staging / source.name)
    command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--onedir', '--windowed',
        '--name', 'SmartTray', '--paths', str(ROOT / 'src'), '--icon', str(icon_path),
        '--add-data', str(staging) + ';data',
        '--add-data', str(ROOT/'tests/fixtures/config') + ';demo-data',
        '--add-data', str(qml_staging) + ';smart_tray/qml',
        '--distpath', str(args.distpath), '--workpath', str(ROOT / 'build/pyinstaller-public'),
        '--specpath', str(ROOT / 'build'), '--exclude-module', 'pytest',
        '--exclude-module', 'PySide6.QtWebEngineCore', '--exclude-module', 'PySide6.QtWebEngineWidgets',
        '--exclude-module', 'smart_tray.rgbic_scene_library',
        '--exclude-module', 'smart_tray.rgbic_scene_protocol',
        '--exclude-module', 'smart_tray.rgbic_cloud_logs',
        str(ROOT / 'scripts/beta_entry.py')]
    subprocess.run(command, cwd=ROOT, check=True)
    manifest = {'version': VERSION, 'format': 'onedir', 'frontend': 'Qt Quick / QML',
        'data_files': files, 'qml_files': sorted(p.name for p in qml_files),
        'credentials_included': False, 'reference_videos_included': False,
        'reference_photos_included': False}
    (args.distpath/'SmartTray/build-info.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print('Built public configuration-free SmartTray.exe')


if __name__ == '__main__':
    main()
