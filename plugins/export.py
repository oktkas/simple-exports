"""Export front.png, back.png and schematic.png for a KiCad project.

Kept free of pcbnew so it can be run and tested outside the PCB editor:
    python export.py BOARD.kicad_pcb
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

import wx

RENDER_SIZE = (2400, 1800)
PADDING = 16            # px of transparent border kept around the trimmed board
SCHEMATIC_WIDTH = 2400
INKSCAPE_CANDIDATES = [
    os.path.join(os.environ.get('ProgramFiles', r'C:\Program Files'), 'Inkscape', 'bin', 'inkscape.com'),
    os.path.join(os.environ.get('ProgramFiles', r'C:\Program Files'), 'Inkscape', 'bin', 'inkscape.exe'),
    '/Applications/Inkscape.app/Contents/MacOS/inkscape',
]


def _tool(name, candidates=()):
    exe = name + ('.exe' if os.name == 'nt' else '')
    for path in [os.path.join(os.path.dirname(sys.executable), exe), *candidates]:
        if os.path.isfile(path):
            return path
    return shutil.which(name)


def _run(args):
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    result = subprocess.run(args, capture_output=True, text=True, encoding='utf-8',
                            errors='replace', creationflags=flags)
    if result.returncode != 0:
        raise RuntimeError(f'{os.path.basename(args[0])} failed:\n{result.stderr or result.stdout}')


def _trim(png):
    """Crop a transparent PNG to its opaque pixels plus PADDING."""
    image = wx.Image(png, wx.BITMAP_TYPE_PNG)
    if not image.HasAlpha():
        return
    w, h = image.GetWidth(), image.GetHeight()
    alpha = bytes(image.GetAlpha())
    top = bottom = None
    left, right = w, 0
    for y in range(h):
        row = alpha[y * w:(y + 1) * w]
        if row.count(0) == w:
            continue
        top = y if top is None else top
        bottom = y
        left = min(left, w - len(row.lstrip(b'\0')))
        right = max(right, len(row.rstrip(b'\0')))
    if top is None:
        return
    x0, y0 = max(left - PADDING, 0), max(top - PADDING, 0)
    x1, y1 = min(right + PADDING, w), min(bottom + 1 + PADDING, h)
    image.GetSubImage(wx.Rect(x0, y0, x1 - x0, y1 - y0)).SaveFile(png, wx.BITMAP_TYPE_PNG)


def _svg_to_png(svg, png):
    inkscape = _tool('inkscape', INKSCAPE_CANDIDATES)
    if inkscape:
        _run([inkscape, svg, '--export-type=png', f'--export-filename={png}',
              f'--export-width={SCHEMATIC_WIDTH}'])
        return
    # wx's built-in SVG rasteriser; it skips embedded bitmaps such as logos.
    with open(svg, encoding='utf-8') as f:
        box = [float(v) for v in re.search(r'viewBox="([^"]+)"', f.read()).group(1).split()]
    size = wx.Size(SCHEMATIC_WIDTH, round(SCHEMATIC_WIDTH * box[3] / box[2]))
    bitmap = wx.BitmapBundle.FromSVGFile(svg, size).GetBitmap(size)
    bitmap.ConvertToImage().SaveFile(png, wx.BITMAP_TYPE_PNG)


def export(board, progress=lambda step: None):
    """Write img/front.png, back.png and schematic.png next to the board.

    Calls progress(text) before each step and returns the written paths.
    """
    kicad_cli = _tool('kicad-cli')
    if not kicad_cli:
        raise RuntimeError('kicad-cli was not found next to KiCad or on PATH.')
    project_dir = os.path.dirname(os.path.abspath(board))
    out_dir = os.path.join(project_dir, 'img')
    os.makedirs(out_dir, exist_ok=True)
    written = []

    for side, name in (('top', 'front'), ('bottom', 'back')):
        progress(f'Rendering {name}')
        png = os.path.join(out_dir, name + '.png')
        _run([kicad_cli, 'pcb', 'render', board, '-o', png, '--side', side,
              '--width', str(RENDER_SIZE[0]), '--height', str(RENDER_SIZE[1]),
              '--quality', 'basic', '--use-board-stackup-colors',
              '--background', 'transparent'])
        _trim(png)
        written.append(png)

    schematic = os.path.splitext(board)[0] + '.kicad_sch'
    if os.path.isfile(schematic):
        progress('Exporting schematic')
        with tempfile.TemporaryDirectory() as tmp:
            _run([kicad_cli, 'sch', 'export', 'svg', '-o', tmp, schematic])
            # A hierarchical design gives one SVG per sheet; the root sheet
            # carries the project name.
            root = os.path.join(tmp, os.path.splitext(os.path.basename(schematic))[0] + '.svg')
            png = os.path.join(out_dir, 'schematic.png')
            _svg_to_png(root, png)
            written.append(png)
    return written


if __name__ == '__main__':
    app = wx.App(False)
    for path in export(os.path.abspath(sys.argv[1]), progress=print):
        print(path)
