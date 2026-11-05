"""Export front.png, back.png and schematic.png for a KiCad project.

Kept free of pcbnew so it can be run and tested outside the PCB editor:
    python export.py BOARD.kicad_pcb
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading

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


class Cancelled(Exception):
    pass


def _run(args, cancel, env=None):
    """Run a tool to completion, or kill it (and its children) once cancel is set."""
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    with subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                          encoding='utf-8', errors='replace', creationflags=flags,
                          env=env) as proc:
        output = []
        reader = threading.Thread(target=lambda: output.append(proc.stdout.read()), daemon=True)
        reader.start()
        while proc.poll() is None:
            if cancel.wait(0.1):
                if os.name == 'nt':
                    subprocess.run(['taskkill', '/T', '/F', '/PID', str(proc.pid)],
                                   capture_output=True, creationflags=flags)
                else:
                    proc.kill()
                proc.wait()
                raise Cancelled()
        reader.join()
    if proc.returncode != 0:
        raise RuntimeError(f'{os.path.basename(args[0])} failed:\n{"".join(output)}')


def _config_home():
    if os.environ.get('KICAD_CONFIG_HOME'):
        return os.environ['KICAD_CONFIG_HOME']
    if os.name == 'nt':
        return os.path.join(os.environ['APPDATA'], 'kicad')
    if sys.platform == 'darwin':
        return os.path.expanduser('~/Library/Preferences/kicad')
    return os.path.join(os.environ.get('XDG_CONFIG_HOME', os.path.expanduser('~/.config')), 'kicad')


def _render_env(kicad_cli, tmp, shaded):
    """Environment pointing kicad-cli at a copy of the user's KiCad settings
    for '--quality user'. Unshaded turns shadows, reflections and
    post-processing off, so renders look like the 3D viewer's unshaded view;
    shaded turns them on. The floor is always off, keeping the background
    transparent.

    Returns None (use the real settings) if they cannot be found.
    """
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    version = subprocess.run([kicad_cli, '--version'], capture_output=True, text=True,
                             creationflags=flags).stdout.strip()
    series = '.'.join(version.split('.')[:2])          # '10.0.6' -> '10.0'
    src = os.path.join(_config_home(), series)
    if not os.path.isfile(os.path.join(src, '3d_viewer.json')):
        return None
    dst = os.path.join(tmp, series)
    shutil.copytree(src, dst)
    viewer = os.path.join(dst, '3d_viewer.json')
    with open(viewer, encoding='utf-8') as f:
        settings = json.load(f)
    render = settings.setdefault('render', {})
    for key in ('raytrace_shadows', 'raytrace_reflections', 'raytrace_post_processing'):
        render[key] = shaded
    render['raytrace_backfloor'] = False
    with open(viewer, 'w', encoding='utf-8') as f:
        json.dump(settings, f, indent=2)
    return {**os.environ, 'KICAD_CONFIG_HOME': tmp}


TOKENS = re.compile(r'"(?:[^"\\]|\\.)*"|[()]')
MODEL_PATH = re.compile(r'(\(model\s+")((?:[^"\\]|\\.)*)"')


def _without_far_models(text, far_layer, project_dir):
    """Board text with the 3D models removed from footprints on far_layer.

    The result is rendered from another folder, so ${KIPRJMOD} and relative
    model paths are made to point back at the project.
    """
    name_at = lambda start: re.match(r'\(([^\s()"]*)', text[start:start + 64]).group(1)
    stack, children, cut = [], [], []
    for m in TOKENS.finditer(text):
        if m.group() == '(':
            stack.append(m.start())
        elif m.group() == ')' and stack:
            start = stack.pop()
            depth = len(stack)                  # 0 = kicad_pcb, 1 = footprint, 2 = its fields
            if depth == 2:
                children.append((start, m.end()))
            elif depth == 1:
                if name_at(start) == 'footprint':
                    layer = next((re.search(r'"([^"]+)"', text[s:e]) for s, e in children
                                  if name_at(s) == 'layer'), None)
                    if layer and layer.group(1) == far_layer:
                        cut += [(s, e) for s, e in children if name_at(s) == 'model']
                children = []
    pieces, last = [], 0
    for s, e in sorted(cut):
        pieces.append(text[last:s])
        last = e
    text = ''.join(pieces) + text[last:]

    project = project_dir.replace('\\', '/')

    def absolute(m):
        path = m.group(2).replace('${KIPRJMOD}', project).replace('$(KIPRJMOD)', project)
        if not (path.startswith('${') or path.startswith('$(') or os.path.isabs(path)):
            path = project + '/' + path
        return m.group(1) + path + '"'
    return MODEL_PATH.sub(absolute, text)


def _one_sided_board(board, side, tmp):
    """Copy of the board (and its project file) in tmp without the other side's 3D models."""
    with open(board, encoding='utf-8') as f:
        text = f.read()
    far = 'B.Cu' if side == 'top' else 'F.Cu'
    folder = os.path.join(tmp, side)
    os.makedirs(folder)
    copy = os.path.join(folder, os.path.basename(board))
    with open(copy, 'w', encoding='utf-8') as f:
        f.write(_without_far_models(text, far, os.path.dirname(os.path.abspath(board))))
    project = os.path.splitext(board)[0] + '.kicad_pro'
    if os.path.isfile(project):                 # text variables live here
        shutil.copy(project, folder)
    return copy


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


def _svg_to_png(svg, png, cancel):
    inkscape = _tool('inkscape', INKSCAPE_CANDIDATES)
    if inkscape:
        _run([inkscape, svg, '--export-type=png', f'--export-filename={png}',
              f'--export-width={SCHEMATIC_WIDTH}'], cancel)
        return
    # wx's built-in SVG rasteriser; it skips embedded bitmaps such as logos.
    with open(svg, encoding='utf-8') as f:
        box = [float(v) for v in re.search(r'viewBox="([^"]+)"', f.read()).group(1).split()]
    size = wx.Size(SCHEMATIC_WIDTH, round(SCHEMATIC_WIDTH * box[3] / box[2]))
    bitmap = wx.BitmapBundle.FromSVGFile(svg, size).GetBitmap(size)
    bitmap.ConvertToImage().SaveFile(png, wx.BITMAP_TYPE_PNG)


PARTS = ('front', 'back', 'schematic')
STYLES = ('unshaded', 'shaded', 'basic')


def export(board, progress=lambda step: None, cancel=None,
           parts=PARTS, style='unshaded', other_side=False):
    """Write img/front.png, back.png and schematic.png next to the board.

    parts picks which of the three to write. style 'unshaded' renders with the
    3D viewer's settings minus shadows, reflections, post-processing and floor;
    'shaded' keeps those on (floor still off); 'basic' uses kicad-cli's basic
    quality. other_side=False leaves out the 3D
    models of parts on the far side of the board.

    Calls progress(text) before each step and returns the written paths.
    Setting the cancel event stops the running tool and raises Cancelled;
    images finished before that are kept.
    """
    if style not in STYLES:
        raise ValueError(f'style must be one of {STYLES}')
    cancel = cancel or threading.Event()
    kicad_cli = _tool('kicad-cli')
    if not kicad_cli:
        raise RuntimeError('kicad-cli was not found next to KiCad or on PATH.')
    project_dir = os.path.dirname(os.path.abspath(board))
    out_dir = os.path.join(project_dir, 'img')
    os.makedirs(out_dir, exist_ok=True)
    written = []

    sides = [(s, n) for s, n in (('top', 'front'), ('bottom', 'back')) if n in parts]
    if sides:
        with tempfile.TemporaryDirectory() as tmp:
            # 'user' takes the 3D viewer's render settings; 'basic' and 'high'
            # draw copper under the mask in bare-copper orange, tinting a
            # white mask peach.
            env = _render_env(kicad_cli, tmp, style == 'shaded') if style != 'basic' else None
            quality = 'basic' if style == 'basic' else 'user'
            for side, name in sides:
                progress(f'Rendering {name}')
                png = os.path.join(out_dir, name + '.png')
                source = board if other_side else _one_sided_board(board, side, tmp)
                _run([kicad_cli, 'pcb', 'render', source, '-o', png, '--side', side,
                      '--width', str(RENDER_SIZE[0]), '--height', str(RENDER_SIZE[1]),
                      '--quality', quality, '--use-board-stackup-colors',
                      '--background', 'transparent'], cancel, env)
                _trim(png)
                written.append(png)

    schematic = os.path.splitext(board)[0] + '.kicad_sch'
    if 'schematic' in parts and os.path.isfile(schematic):
        progress('Exporting schematic')
        with tempfile.TemporaryDirectory() as tmp:
            _run([kicad_cli, 'sch', 'export', 'svg', '-o', tmp, schematic], cancel)
            # A hierarchical design gives one SVG per sheet; the root sheet
            # carries the project name.
            root = os.path.join(tmp, os.path.splitext(os.path.basename(schematic))[0] + '.svg')
            png = os.path.join(out_dir, 'schematic.png')
            _svg_to_png(root, png, cancel)
            written.append(png)
    return written


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Export board and schematic images.')
    parser.add_argument('board')
    parser.add_argument('--only', nargs='+', choices=PARTS, default=list(PARTS))
    parser.add_argument('--style', choices=STYLES, default='unshaded')
    parser.add_argument('--other-side', action='store_true',
                        help="also show the far side's parts")
    args = parser.parse_args()
    app = wx.App(False)
    for path in export(os.path.abspath(args.board), print, None,
                       args.only, args.style, args.other_side):
        print(path)
