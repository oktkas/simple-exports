import os
import threading

import pcbnew
import wx

from . import export

HERE = os.path.dirname(__file__)
NAME = 'Simple Exports'
WIDTH = 360

# Last choices, kept while KiCad runs.
options = {'parts': set(export.PARTS), 'style': 'unshaded', 'other_side': False,
           'default_colors': False}


class ExportDialog(wx.Dialog):
    """One window for the whole run: options, then progress, then the result."""

    def __init__(self, parent, board):
        super().__init__(parent, title=NAME)
        self.board = board
        self.folder = os.path.join(os.path.dirname(board), 'img')
        self.cancel = threading.Event()
        self.state = 'options'                  # options -> running -> done

        icon = wx.StaticBitmap(self, bitmap=wx.Bitmap(os.path.join(HERE, 'icon_48.png')))
        self.heading = wx.StaticText(self, label='Export images')
        self.heading.SetFont(self.heading.GetFont().Bold().Scaled(1.25))
        self.detail = wx.StaticText(self, label=f'Into {self.folder}', size=(WIDTH, -1))
        self.detail.Wrap(WIDTH)

        # Options
        self.choices = wx.BoxSizer(wx.VERTICAL)
        self.part_boxes = {}
        labels = {'front': 'Front render (front.png)', 'back': 'Back render (back.png)',
                  'schematic': 'Schematic (schematic.png)'}
        images = wx.StaticBoxSizer(wx.VERTICAL, self, 'Images')
        for part in export.PARTS:
            box = wx.CheckBox(images.GetStaticBox(), label=labels[part])
            box.SetValue(part in options['parts'])
            box.Bind(wx.EVT_CHECKBOX, self.on_change)
            images.Add(box, 0, wx.ALL, 4)
            self.part_boxes[part] = box
        self.choices.Add(images, 0, wx.EXPAND)

        board_box = wx.StaticBoxSizer(wx.VERTICAL, self, 'Board renders')
        panel = board_box.GetStaticBox()
        self.unshaded = wx.RadioButton(panel, label='Unshaded (your 3D viewer settings)', style=wx.RB_GROUP)
        self.shaded = wx.RadioButton(panel, label='Shaded (with shadows and reflections)')
        self.basic = wx.RadioButton(panel, label='Basic (kicad-cli basic quality)')
        self.unshaded.SetToolTip('Shadows, reflections, post-processing and the floor turned off.')
        self.shaded.SetToolTip('Your 3D viewer settings with shadows, reflections and post-processing '
                               'on; the floor stays off. Slower.')
        self.basic.SetToolTip('Flat, saturated mask colours; copper under the mask can tint light masks.')
        self.styles = {'unshaded': self.unshaded, 'shaded': self.shaded, 'basic': self.basic}
        self.styles[options['style']].SetValue(True)
        self.other_side = wx.CheckBox(panel, label='Show parts on the other side')
        self.other_side.SetValue(options['other_side'])
        self.other_side.SetToolTip('Off: each render shows only the parts mounted on that side.')
        for control in self.styles.values():
            board_box.Add(control, 0, wx.ALL, 4)
        board_box.Add(self.other_side, 0, wx.LEFT | wx.RIGHT | wx.TOP | wx.BOTTOM, 4)
        self.board_box = board_box
        self.choices.Add(board_box, 0, wx.EXPAND | wx.TOP, 10)

        schematic_box = wx.StaticBoxSizer(wx.VERTICAL, self, 'Schematic')
        self.default_colors = wx.CheckBox(schematic_box.GetStaticBox(), label='Use the default colour scheme')
        self.default_colors.SetValue(options['default_colors'])
        self.default_colors.SetToolTip("Off: the colour theme selected in the schematic editor.\n"
                                       "On: KiCad's default schematic colours.")
        schematic_box.Add(self.default_colors, 0, wx.ALL, 4)
        self.choices.Add(schematic_box, 0, wx.EXPAND | wx.TOP, 10)

        # Progress
        self.gauge = wx.Gauge(self, range=100, size=(WIDTH, 6))
        self.gauge.Hide()

        self.open = wx.Button(self, label='Open folder')
        self.go = wx.Button(self, wx.ID_OK, label='Export')
        self.close = wx.Button(self, wx.ID_CANCEL)
        self.open.Hide()
        self.open.Bind(wx.EVT_BUTTON, lambda _: os.startfile(self.folder))
        self.go.Bind(wx.EVT_BUTTON, self.start)
        self.close.Bind(wx.EVT_BUTTON, self.on_close)
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.go.SetDefault()

        text = wx.BoxSizer(wx.VERTICAL)
        text.Add(self.heading)
        text.Add(self.detail, 0, wx.TOP, 4)
        text.Add(self.choices, 0, wx.TOP | wx.EXPAND, 14)
        text.Add(self.gauge, 0, wx.TOP | wx.EXPAND, 12)
        top = wx.BoxSizer(wx.HORIZONTAL)
        top.Add(icon, 0, wx.RIGHT, 16)
        top.Add(text, 1)
        buttons = wx.BoxSizer(wx.HORIZONTAL)
        buttons.AddStretchSpacer()
        buttons.Add(self.open, 0, wx.RIGHT, 8)
        buttons.Add(self.go, 0, wx.RIGHT, 8)
        buttons.Add(self.close)
        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(top, 0, wx.ALL | wx.EXPAND, 20)
        outer.Add(buttons, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, 20)
        self.SetSizerAndFit(outer)
        self.on_change(None)
        self.CentreOnParent()

        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, lambda _: self.gauge.Pulse(), self.timer)

    def selected(self):
        return [p for p in export.PARTS if self.part_boxes[p].GetValue()]

    def on_change(self, _):
        parts = self.selected()
        self.go.Enable(bool(parts))
        renders = 'front' in parts or 'back' in parts
        for control in (*self.styles.values(), self.other_side):
            control.Enable(renders)
        self.default_colors.Enable('schematic' in parts)

    def start(self, _):
        parts = self.selected()
        style = next(name for name, button in self.styles.items() if button.GetValue())
        other_side = self.other_side.GetValue()
        default_colors = self.default_colors.GetValue()
        options.update(parts=set(parts), style=style, other_side=other_side,
                       default_colors=default_colors)

        self.state = 'running'
        self.choices.ShowItems(False)
        self.go.Hide()
        self.gauge.Show()
        self.heading.SetLabel('Exporting images')
        self.detail.SetLabel('Starting')
        self.close.SetFocus()
        self.Layout()
        self.Fit()
        self.timer.Start(50)
        threading.Thread(target=self.work, args=(parts, style, other_side, default_colors), daemon=True).start()

    def work(self, parts, style, other_side, default_colors):
        try:
            written = export.export(self.board, lambda step: wx.CallAfter(self.detail.SetLabel, step + '...'),
                                    self.cancel, parts, style, other_side, default_colors)
        except export.Cancelled:
            wx.CallAfter(self.finish, 'Export cancelled', 'Images finished before cancelling were kept.', False)
        except Exception as error:
            wx.CallAfter(self.finish, 'Export failed', str(error), False)
        else:
            count = f'{len(written)} image' + ('' if len(written) == 1 else 's')
            names = ', '.join(os.path.basename(p) for p in written)
            wx.CallAfter(self.finish, f'Exported {count}', f'{names}\nin {self.folder}', bool(written))

    def finish(self, heading, detail, ok):
        self.timer.Stop()
        self.gauge.SetValue(100 if ok else 0)
        self.heading.SetLabel(heading)
        self.detail.SetLabel(detail)
        self.detail.Wrap(WIDTH)
        self.open.Show(ok)
        self.close.SetLabel('Close')
        self.close.Enable()
        (self.open if ok else self.close).SetFocus()
        self.state = 'done'
        self.Layout()
        self.Fit()

    def on_close(self, event):
        if self.state != 'running':
            self.EndModal(wx.ID_CLOSE)
        elif not self.cancel.is_set():
            # The worker kills the running tool and reports back via finish().
            self.cancel.set()
            self.close.Disable()
            self.detail.SetLabel('Cancelling...')


class SimpleExports(pcbnew.ActionPlugin):
    def defaults(self):
        self.name = NAME
        self.category = 'Export'
        self.description = 'Render front.png, back.png and schematic.png into the project img folder'
        self.show_toolbar_button = True
        self.icon_file_name = os.path.join(HERE, 'icon.png')

    def Run(self):
        board = pcbnew.GetBoard()
        path = board.GetFileName()
        parent = wx.FindWindowByName('PcbFrame')
        if not path:
            wx.MessageBox('Save the board first.', NAME, wx.ICON_WARNING, parent)
            return
        if board.IsModified():
            # kicad-cli renders the files on disk, not the open editor.
            answer = wx.MessageBox('The board has unsaved changes. Save it before exporting?',
                                   NAME, wx.YES_NO | wx.CANCEL | wx.ICON_QUESTION, parent)
            if answer == wx.CANCEL:
                return
            if answer == wx.YES:
                pcbnew.SaveBoard(path, board)
        dialog = ExportDialog(parent, path)
        dialog.ShowModal()
        dialog.Destroy()


SimpleExports().register()
