# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com
'''


import os
import winreg
import wx

import eapo

from meterview import FPS
from meterview import MeterView
from rack import GAP
from rack import MARGIN
from rack import RackView
from rackui import GRAPHICS
from settingsbox import SettingsBox
from sidemenu import SideMenu
from titlebar import TitleBar
from tray import TrayIcon
from utilities import APP_NAME
from utilities import THEMES
from utilities import apply_accent
from utilities import apply_clip_siblings
from utilities import apply_no_caption
from utilities import apply_titlebar_theme
from utilities import cancel_job
from utilities import finish_jobs
from utilities import get_asset_path
from utilities import get_frame_margins
from utilities import load_settings
from utilities import run_latest
from utilities import save_settings


HOVER_INTERVAL = 120
SAVE_DELAY = 600
WRITE_DELAY = 120
DEFAULT_SIZE = (860, 900)
MIN_SIZE = (400, 480)

FRAME_STYLE = wx.DEFAULT_FRAME_STYLE & ~wx.CAPTION

MIN_VISIBLE_WIDTH = 120
MIN_VISIBLE_HEIGHT = 32

MENU_ITEMS = (('Rack', 'rack'), None, ('Settings', 'settings'))


def is_windows_dark():
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize')
        value, _ = winreg.QueryValueEx(key, 'AppsUseLightTheme')
        winreg.CloseKey(key)
        return value == 0
    except OSError:
        return True


class MainFrame(wx.Frame):

    stored_rect = None
    restore_bounds = None
    ready = False
    saver = None
    writer = None
    written = None
    tray = None
    quitting = False

    def __init__(self):
        settings = load_settings()
        super().__init__(None, title=APP_NAME, size=wx.Size(*DEFAULT_SIZE),
                         style=FRAME_STYLE)
        apply_no_caption(self)
        self.SetMinSize(wx.Size(*MIN_SIZE))

        self.accent_name = settings.get('accent', 'blue')
        apply_accent(self.accent_name)
        self.theme_name = self.resolve_theme(settings.get('theme', 'dark'))
        theme = THEMES[self.theme_name]

        self.set_icon()

        self.book = wx.Simplebook(self)
        self.rackpage = wx.Panel(self.book)
        # erasing first shows the bare page between the two repaints
        self.rackpage.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.rackpage.Bind(wx.EVT_ERASE_BACKGROUND, lambda event: None)
        self.rackpage.Bind(wx.EVT_PAINT, lambda event: wx.PaintDC(self.rackpage))
        self.meters = MeterView(self.rackpage, self.store_settings,
                                settings.get('meters_folded', False),
                                settings.get('meters_pinned', True),
                                settings.get('meters_parts'))
        self.rack = RackView(self.rackpage, theme, settings.get('chain', []),
                             settings.get('power', True), self.on_rack_change,
                             settings.get('mixer', {}))
        # the unpinned analyzer floats over the rack, so the rack must clip siblings
        apply_clip_siblings(self.rack)
        self.meters.Raise()
        self.meters.on_height = self.place_rackpage
        self.meters.on_wheel_rack = self.rack.on_wheel
        self.rack.on_scroll = self.place_meters
        self.rack.analyzer = self.meters
        self.rackpage.Bind(wx.EVT_SIZE, lambda event: (self.place_rackpage(), event.Skip()))
        self.settings_folds = set(settings.get('settings_folded', []))
        self.settingsbox = SettingsBox(self.book, theme, settings, self.on_settings,
                                       self.on_unlink, self.settings_folds, self.store_settings)
        for page in (self.rackpage, self.settingsbox):
            self.book.AddPage(page, '')

        self.titlebar = TitleBar(self, theme, self.on_menu, self.toggle_maximize)
        self.sidemenu = SideMenu(self, theme, MENU_ITEMS, self.on_select)
        # the drawer floats over the page, so the page must clip siblings
        apply_clip_siblings(self.book)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.titlebar, 0, wx.EXPAND)
        sizer.Add(self.book, 1, wx.EXPAND)
        self.SetSizer(sizer)

        self.apply_theme()
        self.on_settings()

        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_tick, self.timer)
        # Windows runs its own loop while the window moves or sizes: CallAfter waits there,
        # timer messages still come
        self.sizing = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_sizing, self.sizing)
        self.Bind(wx.EVT_MOVE_START, self.on_move_start)
        self.Bind(wx.EVT_MOVE_END, self.on_move_end)
        self.Bind(wx.EVT_SIZE, self.on_size)
        self.Bind(wx.EVT_MAXIMIZE, self.on_maximize)
        self.Bind(wx.EVT_CHAR_HOOK, self.on_char)
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.timer.Start(HOVER_INTERVAL)
        self.restore_rect(settings)
        self.ready = True
        # the engine file may have changed while the app was closed
        self.write_rack()

    def place_rackpage(self):
        self.rackpage.Freeze()
        try:
            self.lay_rackpage()
        finally:
            self.rackpage.Thaw()

    def lay_rackpage(self):
        width, height = self.rackpage.GetClientSize()
        meters = self.meters
        meters.flowing = self.rack.get_column_count(width) > 1
        if meters.flowing:
            meters.left_margin = meters.right_margin = 0
            self.rack.bottom_space = 0
            self.rack.top_gap = MARGIN
            self.rack.SetSize(0, 0, width, height)
            self.place_meters()
            self.meters.Raise()
            self.rack.clamp()
            self.rack.Refresh()
            return
        meters.left_margin = MARGIN
        # keep the rack scrollbar clear of the floating analyzer
        meters.right_margin = MARGIN if meters.pinned else 0
        meters_width = width if meters.pinned else max(1, width - MARGIN)
        meter_height = meters.get_height(meters_width)
        meters.SetMinSize(wx.Size(-1, meter_height))
        if meters.pinned:
            self.rack.bottom_space = 0
            self.rack.top_gap = GAP
            self.rack.SetSize(0, meter_height, width, max(1, height - meter_height))
            meters.SetSize(0, 0, meters_width, meter_height)
        else:
            self.rack.bottom_space = meter_height
            self.rack.top_gap = MARGIN
            self.rack.SetSize(0, 0, width, height)
            meters.SetSize(0, self.rack.meters_y - self.rack.offset, meters_width, meter_height)
        self.meters.Raise()
        self.rack.clamp()
        self.rack.Refresh()

    def place_meters(self):
        if not self.rack:
            return
        if self.meters.flowing:
            rect = self.rack.analyzer_slot.rect
            # the slot exists only after the rack draws in columns
            if self.rack.columns < 2 or rect.width <= 0:
                return
            target = wx.Rect(rect.x, rect.y - self.rack.offset, rect.width, rect.height)
            if self.meters.GetRect() != target:
                self.meters.SetSize(target)
            return
        if self.meters.pinned:
            return
        y = self.rack.meters_y - self.rack.offset
        if self.meters.GetPosition().y != y:
            self.meters.SetPosition(wx.Point(0, y))

    def is_rect_visible(self, rect):
        for index in range(wx.Display.GetCount()):
            shared = wx.Display(index).GetClientArea().Intersect(rect)
            if shared.width >= MIN_VISIBLE_WIDTH and shared.height >= MIN_VISIBLE_HEIGHT:
                return True
        return False

    def centre_on_primary(self):
        primary = wx.Display(wx.Display.GetFromPoint(wx.Point(0, 0))).GetClientArea()
        width, height = self.GetSize()
        self.SetPosition(wx.Point(primary.x + (primary.width - width) // 2,
                                  primary.y + (primary.height - height) // 2))

    def restore_rect(self, settings):
        stored = settings.get('rect')
        if stored and len(stored) == 4:
            rect = wx.Rect(*stored)
            if self.is_rect_visible(rect):
                self.SetRect(rect)
                self.stored_rect = list(stored)
                return
            self.SetSize(rect.GetSize())

        self.centre_on_primary()
        self.stored_rect = list(self.GetRect())

    def set_icon(self):
        path = get_asset_path('icon', 'icon.ico')
        if os.path.exists(path):
            self.SetIcon(wx.Icon(path, wx.BITMAP_TYPE_ICO))

    def apply_theme(self):
        theme = THEMES[self.theme_name]
        self.SetBackgroundColour(wx.Colour(theme['bg']))
        self.book.SetBackgroundColour(wx.Colour(theme['bg']))
        self.titlebar.set_theme(theme)
        self.sidemenu.set_theme(theme)
        self.settingsbox.apply_theme(theme)
        apply_titlebar_theme(self, theme)
        self.Refresh()

    def on_menu(self):
        self.sidemenu.toggle()

    def on_select(self, index):
        self.book.SetSelection(index)
        if self.book.GetPage(index) is self.settingsbox:
            self.settingsbox.refresh_state()
        else:
            self.rack.refresh_state()

    def on_rack_change(self):
        if self.writer is not None and self.writer.IsRunning():
            self.writer.Stop()
        self.writer = wx.CallLater(WRITE_DELAY, self.write_rack)
        self.store_settings()

    def write_rack(self):
        if self.rack.state != 'linked':
            return
        # view-only changes render the same text; skip so the engine does not reload
        text = eapo.render(self.rack.get_chain(), self.rack.power)
        path = os.path.join(self.rack.folder, eapo.OWN_FILE)
        if text == self.written and os.path.exists(path):
            return
        self.written = text
        run_latest(path, eapo.write_later(path, text))

    def on_unlink(self):
        # a queued write would bring the rack file back after unlinking
        if self.rack.folder:
            cancel_job(os.path.join(self.rack.folder, eapo.OWN_FILE))
        self.rack.on_unlink()

    def toggle_maximize(self):
        # Windows maximizes a captionless frame over the taskbar
        if self.restore_bounds is not None:
            bounds, self.restore_bounds = self.restore_bounds, None
            self.SetRect(wx.Rect(*bounds))
        else:
            self.restore_bounds = list(self.GetRect())
            index = max(0, wx.Display.GetFromWindow(self))
            work = wx.Display(index).GetClientArea()
            left, top, right, bottom = get_frame_margins(self)
            self.SetRect(wx.Rect(work.x - left, work.y - top,
                                 work.width + left + right,
                                 work.height + top + bottom))
        self.titlebar.set_maximized(self.restore_bounds is not None)

    def on_maximize(self, event):
        if not self.IsMaximized():
            return
        self.Maximize(False)
        if self.restore_bounds is None:
            self.toggle_maximize()

    def on_char(self, event):
        if event.GetKeyCode() == wx.WXK_ESCAPE and self.sidemenu.is_open():
            self.sidemenu.close()
            return
        if event.GetKeyCode() == wx.WXK_ESCAPE and self.rack.cancel_remove():
            return
        event.Skip()

    @staticmethod
    def resolve_theme(choice):
        if choice == 'auto':
            return 'dark' if is_windows_dark() else 'light'
        return choice if choice in THEMES else 'dark'

    def on_settings(self):
        style = self.GetWindowStyle()
        if self.settingsbox.ontop.GetValue():
            self.SetWindowStyle(style | wx.STAY_ON_TOP)
        else:
            self.SetWindowStyle(style & ~wx.STAY_ON_TOP)
        if self.rack.wide != self.settingsbox.wide.GetValue():
            self.rack.set_wide(self.settingsbox.wide.GetValue())
            self.place_rackpage()

        theme_name = self.resolve_theme(self.settingsbox.theme_choice.GetValue())
        accent_name = self.settingsbox.accent_choice.GetValue()
        if theme_name != self.theme_name or accent_name != self.accent_name:
            self.theme_name = theme_name
            self.accent_name = accent_name
            apply_accent(self.accent_name)
            self.apply_theme()
        if self.settingsbox.tray.GetValue() and self.tray is None:
            self.tray = TrayIcon(self)
        elif not self.settingsbox.tray.GetValue() and self.tray is not None:
            self.remove_tray()
        self.store_settings()

    def remove_tray(self):
        self.tray.RemoveIcon()
        self.tray.Destroy()
        self.tray = None

    def quit(self):
        self.quitting = True
        self.Close(True)

    def show_window(self):
        if self.IsIconized():
            self.Iconize(False)
        self.Show()
        self.Raise()
        self.SetFocus()

    def on_size(self, event):
        self.sidemenu.place(TitleBar.HEIGHT)
        event.Skip()

    def on_move_start(self, event):
        self.sizing.Start(1000 // FPS)
        event.Skip()

    def on_move_end(self, event):
        self.sizing.Stop()
        event.Skip()

    def on_sizing(self, event):
        self.meters.tick()
        self.rack.tick()

    def on_tick(self, event):
        # the drawer also closes on its own (outside click, Esc, lost capture)
        self.titlebar.set_menu_open(self.sidemenu.is_open())

    def store_settings(self):
        if not self.ready:
            return
        if self.saver is not None and self.saver.IsRunning():
            self.saver.Stop()
        self.saver = wx.CallLater(SAVE_DELAY, self.flush_settings)

    def flush_settings(self):
        settings = {
            # the choice, 'auto' too, not the theme it resolved to
            'theme': self.settingsbox.theme_choice.GetValue(),
            'accent': self.accent_name,
            'settings_folded': sorted(self.settings_folds),
            'on_top': self.settingsbox.ontop.GetValue(),
            'tray_icon': self.settingsbox.tray.GetValue(),
            'close_to_tray': self.settingsbox.close_to_tray.GetValue(),
            'wide_layout': self.settingsbox.wide.GetValue(),
            'rect': self.stored_rect,
            'power': self.rack.power,
            'chain': self.rack.get_chain(),
            'mixer': self.rack.mixer.data,
            'meters_folded': self.meters.folded,
            'meters_pinned': self.meters.pinned,
            'meters_parts': self.meters.parts,
        }
        save_settings(settings)

    def on_close(self, event):
        if (self.tray is not None and self.settingsbox.close_to_tray.GetValue()
                and not self.quitting and event.CanVeto()):
            event.Veto()
            if self.restore_bounds is not None:
                self.stored_rect = list(self.restore_bounds)
            elif self.IsIconized() is False and self.IsMaximized() is False:
                self.stored_rect = list(self.GetRect())
            self.flush_settings()
            # a second launch may have shown the window behind wx's back
            self.Show(True)
            self.Hide()
            return
        self.timer.Stop()
        self.sizing.Stop()
        if self.saver is not None and self.saver.IsRunning():
            self.saver.Stop()
        if self.writer is not None and self.writer.IsRunning():
            self.writer.Stop()
        self.write_rack()
        self.meters.close()
        self.rack.close()
        # do not leave the engine bypassed after an A/B compare
        from automastermeter import READER
        READER.set_bypass(False)
        # release the mouse capture before the frame goes
        self.sidemenu.close()
        # close() starts the slide timer, which crashes (0xc0000374) after destroy
        self.sidemenu.timer.Stop()
        if self.restore_bounds is not None:
            self.stored_rect = list(self.restore_bounds)
        elif self.IsIconized() is False and self.IsMaximized() is False:
            self.stored_rect = list(self.GetRect())
        self.flush_settings()
        # the last rack write and settings must land before the process goes
        finish_jobs()
        # a live tray icon keeps the app running after the frame is gone
        if self.tray is not None:
            self.remove_tray()
        event.Skip()


def launch_mainapp():
    app = wx.App(False)
    frame = MainFrame()
    frame.Show()
    apply_titlebar_theme(frame, THEMES[frame.theme_name])
    app.MainLoop()
    # cached graphics objects must go before wx shuts GDI+ down, or exit crashes (0xc0000005)
    GRAPHICS.clear()
