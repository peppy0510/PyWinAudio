# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com
'''


import os
import wx

import eapo

from meterview import MeterView
from rack import GAP
from rack import MARGIN
from rack import RackView
from settingsbox import SettingsBox
from sidemenu import SideMenu
from titlebar import TitleBar
from utilities import APP_NAME
from utilities import THEMES
from utilities import apply_clip_siblings
from utilities import apply_no_caption
from utilities import apply_titlebar_theme
from utilities import get_asset_path
from utilities import get_frame_margins
from utilities import load_settings
from utilities import save_settings


HOVER_INTERVAL = 120
SAVE_DELAY = 600
# 랙을 고친 뒤 엔진에 넘기기까지. 손잡이를 돌리는 동안 파일을 너무 자주 바꾸지 않게.
WRITE_DELAY = 120
RETRY_DELAY = 250
DEFAULT_SIZE = (860, 900)
MIN_SIZE = (400, 480)

# 캡션을 떼고 그 자리를 직접 그린다. 크기 조절과 스냅은 그대로 남는다.
FRAME_STYLE = wx.DEFAULT_FRAME_STYLE & ~wx.CAPTION

# 기억된 위치가 이만큼도 화면에 안 걸리면 사라진 모니터로 본다.
MIN_VISIBLE_WIDTH = 120
MIN_VISIBLE_HEIGHT = 32

PAGE_KEYS = ('rack', 'settings')

MENU_ITEMS = (('Rack', 'rack'), None, ('Settings', 'settings'))


class MainFrame(wx.Frame):

    stored_rect = None
    # 흉내 낸 최대화 이전의 자리. None 이면 최대화 상태가 아니다.
    restore_bounds = None
    ready = False
    saver = None
    writer = None
    written = None

    def __init__(self):
        settings = load_settings()
        super().__init__(None, title=APP_NAME, size=wx.Size(*DEFAULT_SIZE),
                         style=FRAME_STYLE)
        apply_no_caption(self)
        self.SetMinSize(wx.Size(*MIN_SIZE))

        self.theme_name = settings.get('theme', 'dark')
        theme = THEMES[self.theme_name]

        self.set_icon()

        self.book = wx.Simplebook(self)
        # 계기판은 랙 위에 고정해 두고 랙만 굴린다. 따로 다시 그려져 랙을 건드리지 않는다.
        self.rackpage = wx.Panel(self.book)
        # 바탕은 랙과 계기판이 늘 덮는다. 크기가 바뀔 때마다 바탕을 먼저 지우면 둘이 다시 그려지기 전에
        # 지운 색이 비쳐 깜빡였다(사용자) — 지우지 않는다.
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
        # 사이저를 쓰지 않고 두 창을 직접 놓는다. 핀을 뺀 Analyzer 판은 랙 위에 겹쳐 떠서
        # 랙이 굴러가는 만큼 같이 올라간다. 랙은 그 아래를 칠하지 않게 형제를 클립한다.
        apply_clip_siblings(self.rack)
        self.meters.Raise()
        self.meters.on_height = self.place_rackpage
        self.meters.on_wheel_rack = self.rack.on_wheel
        self.rack.on_scroll = self.place_meters
        self.rack.analyzer = self.meters
        self.rackpage.Bind(wx.EVT_SIZE, lambda event: (self.place_rackpage(), event.Skip()))
        self.settingsbox = SettingsBox(self.book, theme, settings, self.on_settings,
                                       self.on_unlink)
        for page in (self.rackpage, self.settingsbox):
            self.book.AddPage(page, '')

        self.titlebar = TitleBar(self, theme, self.on_menu, self.toggle_maximize)
        self.sidemenu = SideMenu(self, theme, MENU_ITEMS, self.on_select)
        # 서랍은 페이지 위에 떠 있다. 페이지 쪽이 형제를 클립해 주어야 살아남는다.
        apply_clip_siblings(self.book)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.titlebar, 0, wx.EXPAND)
        sizer.Add(self.book, 1, wx.EXPAND)
        self.SetSizer(sizer)

        self.apply_theme()
        self.on_settings()

        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_tick)
        self.Bind(wx.EVT_SIZE, self.on_size)
        self.Bind(wx.EVT_MAXIMIZE, self.on_maximize)
        self.Bind(wx.EVT_CHAR_HOOK, self.on_char)
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.timer.Start(HOVER_INTERVAL)
        self.restore_rect(settings)
        self.restore_page(settings)
        self.ready = True
        # 앱을 닫아 둔 사이 엔진 쪽 파일이 바뀌었을 수 있다. 랙이 정본이니 한 번 써 둔다.
        self.write_rack()

    def restore_page(self, settings):
        stored = settings.get('page')
        index = PAGE_KEYS.index(stored) if stored in PAGE_KEYS else 0
        self.book.SetSelection(index)
        self.sidemenu.set_selection(self.get_menu_index(index))

    def place_rackpage(self):
        # 계기판과 랙을 하나씩 옮기는 사이의 반쯤 놓인 모습이 그려지지 않게, 다 옮긴 뒤 한 번에 그린다.
        self.rackpage.Freeze()
        try:
            self.lay_rackpage()
        finally:
            self.rackpage.Thaw()

    def lay_rackpage(self):
        width, height = self.rackpage.GetClientSize()
        # 한 단일 때: 핀을 꽂으면 계기판은 랙 위에 고정, 빼면 랙 맨 아래(ADD 다음)에 함께 구른다.
        meters = self.meters
        # 랙이 여러 단이면 판도 랙의 한 칸이다. 자리는 랙이 정하고, 랙을 그린 뒤 place_meters 가 옮긴다.
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
        # 핀을 빼면 판이 랙 위에 겹친다. 오른쪽 여백은 비워 랙 스크롤바가 판 뒤에 숨지 않게.
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
        '''랙이 굴러가거나 장치 수가 바뀔 때마다 핀을 뺀 판을 랙 맨 아래 자리로 옮긴다.'''
        if not self.rack:
            return
        if self.meters.flowing:
            rect = self.rack.analyzer_slot.rect
            # 랙이 아직 여러 단으로 그려지기 전이면 자리가 없다. 그린 뒤 다시 불린다.
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

    def get_menu_index(self, page):
        '''구분선이 끼어 있어 항목의 차례와 페이지의 차례가 그 뒤로 어긋난다.'''
        count = -1
        for index, item in enumerate(MENU_ITEMS):
            if item:
                count += 1
                if count == page:
                    return index
        return 0


    def get_page_key(self):
        index = self.book.GetSelection()
        return PAGE_KEYS[index] if 0 <= index < len(PAGE_KEYS) else PAGE_KEYS[0]

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
        key = PAGE_KEYS[index]
        if key == 'settings':
            self.settingsbox.refresh_state()
        elif key == 'rack':
            self.rack.refresh_state()
        self.store_settings()

    def on_rack_change(self):
        if self.writer is not None and self.writer.IsRunning():
            self.writer.Stop()
        self.writer = wx.CallLater(WRITE_DELAY, self.write_rack)
        self.store_settings()

    def write_rack(self):
        '''못 쓰면 버리지 않고 잠시 뒤 다시 쓴다. 마지막 변경이 엔진에 못 가면 다음 변경
        때까지 소리가 화면과 어긋난 채로 남는다.'''
        if self.rack.state != 'linked':
            return
        # 접기처럼 보기만 바뀐 것은 같은 글이 나온다. 엔진이 다시 읽을 까닭이 없으니 쓰지 않는다.
        text = eapo.render(self.rack.get_chain(), self.rack.power)
        path = os.path.join(self.rack.folder, eapo.OWN_FILE)
        if text == self.written and os.path.exists(path):
            return
        try:
            eapo.write_text(path, text)
            self.written = text
        except OSError:
            if self.writer is not None and self.writer.IsRunning():
                return
            self.writer = wx.CallLater(RETRY_DELAY, self.write_rack)

    def on_unlink(self):
        self.rack.on_unlink()

    def toggle_maximize(self):
        '''캡션이 없는 창을 Windows 가 최대화하면 보이지 않는 여백만큼 화면
        밖으로 넘치고 작업 표시줄까지 덮는다. 작업 영역에 맞춰 직접 채운다.'''
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

    def on_settings(self):
        style = self.GetWindowStyle()
        if self.settingsbox.ontop.GetValue():
            self.SetWindowStyle(style | wx.STAY_ON_TOP)
        else:
            self.SetWindowStyle(style & ~wx.STAY_ON_TOP)
        if self.rack.wide != self.settingsbox.wide.GetValue():
            self.rack.set_wide(self.settingsbox.wide.GetValue())
            self.place_rackpage()

        theme_name = 'dark' if self.settingsbox.dark.GetValue() else 'light'
        if theme_name != self.theme_name:
            self.theme_name = theme_name
            self.apply_theme()
        self.store_settings()

    def on_size(self, event):
        self.sidemenu.place(TitleBar.HEIGHT)
        event.Skip()

    def on_tick(self, event):
        # 서랍은 바깥 누름·ESC·캡처 잃음으로도 닫힌다. 햄버거 표시는 여기서 따라간다.
        self.titlebar.set_menu_open(self.sidemenu.is_open())

    def store_settings(self):
        if not self.ready:
            return
        if self.saver is not None and self.saver.IsRunning():
            self.saver.Stop()
        self.saver = wx.CallLater(SAVE_DELAY, self.flush_settings)

    def flush_settings(self):
        settings = {
            'theme': self.theme_name,
            'on_top': self.settingsbox.ontop.GetValue(),
            'wide_layout': self.settingsbox.wide.GetValue(),
            'page': self.get_page_key(),
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
        self.timer.Stop()
        if self.saver is not None and self.saver.IsRunning():
            self.saver.Stop()
        if self.writer is not None and self.writer.IsRunning():
            self.writer.Stop()
        # 닫을 때는 다시 해 볼 틈이 없다. 마지막 상태를 늘 한 번 더 쓴다.
        self.writer = None
        self.write_rack()
        if self.writer is not None:
            self.writer.Stop()
        self.meters.close()
        self.rack.close()
        # 마우스를 잡은 채로 창이 사라지면 나중에 죽는다. 먼저 놓게 한다.
        self.sidemenu.close()
        if self.restore_bounds is not None:
            self.stored_rect = list(self.restore_bounds)
        elif self.IsIconized() is False and self.IsMaximized() is False:
            self.stored_rect = list(self.GetRect())
        self.flush_settings()
        event.Skip()


def launch_mainapp():
    app = wx.App(False)
    frame = MainFrame()
    frame.Show()
    apply_titlebar_theme(frame, THEMES[frame.theme_name])
    app.MainLoop()
