import os
import threading

import pcbnew
import wx

from . import export

HERE = os.path.dirname(__file__)
NAME = 'Simple Exports'


class ExportDialog(wx.Dialog):
    """One window for the whole run: progress first, then the result."""

    def __init__(self, parent, board):
        super().__init__(parent, title=NAME)
        self.folder = os.path.join(os.path.dirname(board), 'img')

        icon = wx.StaticBitmap(self, bitmap=wx.Bitmap(os.path.join(HERE, 'icon_48.png')))
        self.heading = wx.StaticText(self, label='Exporting images')
        self.heading.SetFont(self.heading.GetFont().Bold().Scaled(1.25))
        self.detail = wx.StaticText(self, label='Starting', size=(360, -1))
        self.gauge = wx.Gauge(self, range=100, size=(360, 6))
        self.open = wx.Button(self, label='Open folder')
        self.close = wx.Button(self, wx.ID_CLOSE)
        self.open.Disable()
        self.close.Disable()
        self.open.Bind(wx.EVT_BUTTON, lambda _: os.startfile(self.folder))
        self.close.Bind(wx.EVT_BUTTON, lambda _: self.EndModal(wx.ID_CLOSE))
        self.Bind(wx.EVT_CLOSE, self.on_close)

        text = wx.BoxSizer(wx.VERTICAL)
        text.Add(self.heading)
        text.Add(self.detail, 0, wx.TOP, 4)
        text.Add(self.gauge, 0, wx.TOP | wx.EXPAND, 12)
        top = wx.BoxSizer(wx.HORIZONTAL)
        top.Add(icon, 0, wx.RIGHT, 16)
        top.Add(text, 1)
        buttons = wx.BoxSizer(wx.HORIZONTAL)
        buttons.AddStretchSpacer()
        buttons.Add(self.open, 0, wx.RIGHT, 8)
        buttons.Add(self.close)
        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(top, 0, wx.ALL | wx.EXPAND, 20)
        outer.Add(buttons, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, 20)
        self.SetSizerAndFit(outer)
        self.CentreOnParent()

        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, lambda _: self.gauge.Pulse(), self.timer)
        self.timer.Start(50)
        threading.Thread(target=self.work, args=(board,), daemon=True).start()

    def work(self, board):
        try:
            written = export.export(board, lambda step: wx.CallAfter(self.detail.SetLabel, step + '...'))
        except Exception as error:
            wx.CallAfter(self.finish, 'Export failed', str(error), False)
        else:
            names = ', '.join(os.path.basename(p) for p in written)
            wx.CallAfter(self.finish, f'Exported {len(written)} images', f'{names}\nin {self.folder}', True)

    def finish(self, heading, detail, ok):
        self.timer.Stop()
        self.gauge.SetValue(100 if ok else 0)
        self.heading.SetLabel(heading)
        self.detail.SetLabel(detail)
        self.detail.Wrap(360)
        self.open.Enable(ok)
        self.close.Enable()
        (self.open if ok else self.close).SetFocus()
        self.Fit()

    def on_close(self, event):
        if self.close.IsEnabled():
            self.EndModal(wx.ID_CLOSE)


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
