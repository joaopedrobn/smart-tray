"""Import a local official library export; no network or device credentials."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from smart_tray.rgbic_scene_library import import_library


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT/'diagnostics/rgbic-scenes/recovered-library.json')
    args = parser.parse_args()
    try:
        with args.input.open('rb') as stream:
            raw = stream.read(5_000_001)
        report = import_library(raw)
        if args.output.resolve() == args.input.resolve():
            raise ValueError('Refuse to overwrite original export')
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    except (OSError, ValueError):
        print('Importacao recusada: arquivo, formato, origem ou dados invalidos. Nenhum comando enviado.')
        return 1
    print(f"Cenas importadas: {report['scene_count']}; rejeitadas: {report['rejected_count']}; Neon World: {report['neon_world_found']}. Nenhum comando enviado.")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
