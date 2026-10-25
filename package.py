"""Build the KiCad Plugin and Content Manager archive: dist/simple-exports-<version>.zip

Install the result in KiCad with Plugin and Content Manager > Install from File.
"""
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).parent
metadata = json.loads((ROOT / 'metadata.json').read_text(encoding='utf-8'))
version = metadata['versions'][0]['version']
archive = ROOT / 'dist' / f'simple-exports-{version}.zip'
archive.parent.mkdir(exist_ok=True)

with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as zf:
    zf.write(ROOT / 'metadata.json', 'metadata.json')
    zf.write(ROOT / 'resources' / 'icon.png', 'resources/icon.png')
    for path in sorted((ROOT / 'plugins').rglob('*')):
        if path.is_file() and '__pycache__' not in path.parts:
            zf.write(path, path.relative_to(ROOT).as_posix())

print(archive)
