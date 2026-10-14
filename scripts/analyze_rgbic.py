"""Compare every saved RGBIC recording offline; never contacts devices/cloud."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from smart_tray.rgbic_analysis import analyze_directory
from smart_tray.rgbic_capture import scene_definition


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', type=Path,
        default=Path(os.environ['LOCALAPPDATA'])/'SmartTray/rgbic-scenes')
    parser.add_argument('--output', type=Path, default=ROOT/'diagnostics/rgbic-scenes/analysis-current.json')
    args = parser.parse_args()
    if args.output.resolve().parent == args.directory.resolve():
        parser.error('Analysis output must stay outside the source catalog')
    report = analyze_directory(args.directory, scene_definition(ROOT/'diagnostics/led-research/schema-current.json'))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'files_scanned': report['files_scanned'], 'records_analyzed': report['records_analyzed'],
        'rejected_count': len(report['rejected']), 'samples': report['sample_count_total'],
        'scene_raw_recordings': report['scene_payloads_observed'], 'writes_sent': 0}, ensure_ascii=True))
    for record in report['records']:
        print(json.dumps({'scene': record['scene'], 'samples': record['sample_count'],
            'changed_dps': list(record['changes']), 'scene_raw_observed': record['scene_raw_observed'],
            'candidate_available': bool(record['candidate'])}, ensure_ascii=True))


if __name__ == '__main__':
    main()
