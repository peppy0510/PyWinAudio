# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com

플러그인이 제 손으로 그리는 편집기를 담는 창. 플러그인은 바꾼 값을 알려 주지 않는
일이 많아(audioMasterAutomate 를 부르지 않는다) 값을 짧은 간격으로 직접 읽어 본다.
'''


import wx

from utilities import THEMES
from utilities import apply_titlebar_theme


IDLE_INTERVAL = 30
# 값 읽기는 쉬는 박자 몇 번에 한 번. 덩어리를 쓰는 플러그인은 읽기가 무겁다.
POLL_EVERY = 8


class EditorFrame(wx.Frame):

    def __init__(self, parent, unit):
        style = (wx.CAPTION | wx.CLOSE_BOX | wx.SYSTEM_MENU | wx.FRAME_FLOAT_ON_PARENT |
                 wx.FRAME_TOOL_WINDOW)
        super().__init__(parent, title=unit.get_title(), style=style)
        self.unit = unit
        self.ticks = 0
        self.panel = wx.Panel(self)
        self.panel.SetBackgroundColour(wx.Colour('#000000'))

        size = unit.plugin.open_editor(self.panel.GetHandle())
        self.SetClientSize(wx.Size(*(size or (480, 320))))
        self.place(parent)

        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_tick)
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.Show()
        apply_titlebar_theme(self, THEMES['dark'])
        self.timer.Start(IDLE_INTERVAL)

    def place(self, parent):
        '''주 창 오른쪽에 붙인다. 자리가 없으면 주 창 위 가운데.'''
        frame = parent.GetScreenRect()
        width, height = self.GetSize()
        index = max(0, wx.Display.GetFromWindow(parent))
        work = wx.Display(index).GetClientArea()
        x = frame.x + frame.width + 8
        if x + width > work.x + work.width:
            x = frame.x + (frame.width - width) // 2
        y = max(work.y, min(frame.y + 80, work.y + work.height - height))
        self.SetPosition(wx.Point(max(work.x, x), y))

    def on_tick(self, event):
        plugin = self.unit.plugin
        if plugin is None:
            return
        plugin.idle()
        # 편집기가 스스로 크기를 바꾸겠다고 하면 창을 맞춘다(Large GUI 같은 단추).
        if plugin.requested_size:
            width, height = plugin.requested_size
            plugin.requested_size = None
            self.SetClientSize(wx.Size(width, height))
        self.ticks += 1
        if self.ticks % POLL_EVERY == 0:
            self.unit.on_editor_poll()

    def on_close(self, event):
        self.timer.Stop()
        plugin = self.unit.plugin
        if plugin is not None:
            plugin.close_editor()
        self.unit.on_editor_closed()
        self.Destroy()
