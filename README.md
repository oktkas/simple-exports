# Simple Exports

A one-click KiCad PCB editor plugin that writes three images into an `img`
folder next to the board:

- `front.png` and `back.png`: orthographic 3D renders in the board's stackup
  colours, trimmed to the board on a transparent background
- `schematic.png`: the root schematic sheet, 2400 px wide

It works on any project with no per-board setup. Parts are drawn from their
3D models. Rendering uses `kicad-cli` from the running KiCad, and the
schematic is rasterised with Inkscape when installed (otherwise with
wxWidgets, which leaves out embedded bitmaps such as title-block logos).
kicad-cli works on the saved files, so the plugin offers to save a modified
board first.

Tested with KiCad 10 on Windows.

## Install

Link (or copy) the `plugins` folder into KiCad's plugin directory under the
name `simple_exports`, then restart the PCB editor or use
*Tools → External Plugins → Refresh Plugins*:

```powershell
New-Item -ItemType Junction `
  -Path "$env:USERPROFILE\Documents\KiCad\10.0\scripting\plugins\simple_exports" `
  -Target "$PWD\plugins"
```

The button appears in the top toolbar and under *Tools → External Plugins*.

## Outside KiCad

`plugins/export.py` does not need pcbnew, so it can run in KiCad's Python:

```powershell
& "C:\Program Files\KiCad\10.0\bin\python.exe" plugins\export.py path\to\board.kicad_pcb
```

## Icon

`icon.svg` is "Image" by Kasanah from the Noun Project
(https://thenounproject.com/icon/image-8290303/), cropped and recoloured.
`plugins/icon.png` (24 px, toolbar) and `plugins/icon_48.png` (dialog) are
rendered from it.
