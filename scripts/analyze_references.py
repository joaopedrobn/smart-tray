"""Decode every reference frame; save representative frames and motion metrics."""
import json
from pathlib import Path
from PIL import Image, ImageChops, ImageStat, ImageDraw
import imageio_ffmpeg

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'diagnostics/reference-analysis'
OUTPUT.mkdir(parents=True, exist_ok=True)
report = []
for name in ('referencia-elgin.mp4.mp4', 'referencia-interface.gif.mp4'):
    source = ROOT / 'references' / name
    reader = imageio_ffmpeg.read_frames(str(source), pix_fmt='rgb24')
    metadata = next(reader)
    width, height = metadata['size']
    fps = metadata['fps']
    selected, motion, previous = [], [], None
    count = 0
    for index, raw in enumerate(reader):
        frame = Image.frombytes('RGB', (width, height), raw)
        reduced = frame.resize((120, max(1, round(height * 120 / width))))
        difference = sum(ImageStat.Stat(ImageChops.difference(reduced, previous)).mean) / 3 if previous else 0
        motion.append({'frame': index, 'seconds': round(index / fps, 3), 'mean_change': round(difference, 3)})
        previous = reduced
        if index % max(1, round(fps / 2)) == 0:
            path = OUTPUT / f'{source.stem}-{index:04d}.png'
            frame.save(path)
            selected.append((index / fps, path))
        count += 1
    columns, cell_w, cell_h = 4, 300, round(height * 300 / width) + 28
    sheet = Image.new('RGB', (columns * cell_w, ((len(selected) + columns - 1) // columns) * cell_h), '#10141c')
    draw = ImageDraw.Draw(sheet)
    for index, (seconds, path) in enumerate(selected):
        frame = Image.open(path)
        frame.thumbnail((cell_w, cell_h - 28))
        x, y = (index % columns) * cell_w, (index // columns) * cell_h
        sheet.paste(frame, (x, y + 24))
        draw.text((x + 8, y + 5), f'{seconds:.2f}s', fill='white')
    sheet.save(OUTPUT / f'{source.stem}-contact.png')
    report.append({'file': name, 'size': [width, height], 'fps': fps, 'decoded_frames': count,
                   'duration': count / fps, 'selected_frames': len(selected),
                   'all_frame_motion': motion})
(OUTPUT / 'analysis.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps([{k: v for k, v in item.items() if k != 'all_frame_motion'} for item in report], indent=2))
