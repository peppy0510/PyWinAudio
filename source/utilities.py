# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com
'''


import asyncio
import ctypes
import json
import os
import threading
import wx

from ctypes import wintypes


APP_NAME = 'PyWinAudio'

CARD_HEIGHT = 54
CARD_RADIUS = 6

TITLEBAR_HEIGHT = 32
CAPTION_WIDTH = 46

GWL_STYLE = -16
WS_CAPTION = 0x00C00000
WS_CLIPSIBLINGS = 0x04000000

SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020

RDW_ALLCHILDREN = 0x0080
RDW_UPDATENOW = 0x0100

DWMWA_EXTENDED_FRAME_BOUNDS = 9
DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_USE_IMMERSIVE_DARK_MODE_BEFORE_20H1 = 19
DWMWA_BORDER_COLOR = 34
DWMWA_CAPTION_COLOR = 35

WM_COPYGLOBALDATA = 0x0049
WM_COPYDATA = 0x004A
WM_DROPFILES = 0x0233
MSGFLT_ALLOW = 1


THEMES = {
    'dark': {
        'bg': '#141517',
        'face': '#1d1f23',
        'rim': '#2b2e33',
        'track': '#2b2e33',
        'text': '#e6e9ed',
        'dim': '#8b929b',
        'accent': '#4c9aff',
        'control': '#26282d',
        'warn': '#ff9a3d',
        'done': '#4c9aff',
        'close': '#c42b1c',
        'titlebar_dark': True,
    },
    'light': {
        'bg': '#f4f5f7',
        'face': '#ffffff',
        'rim': '#d5d9df',
        'track': '#d5d9df',
        'text': '#1d2126',
        'dim': '#6b727c',
        'accent': '#2b6cb0',
        'control': '#e8eaee',
        'warn': '#a2661f',
        'done': '#2b6cb0',
        'close': '#c42b1c',
        'titlebar_dark': False,
    },
}


class WindowRect(ctypes.Structure):
    _fields_ = [('left', ctypes.c_long), ('top', ctypes.c_long),
                ('right', ctypes.c_long), ('bottom', ctypes.c_long)]


def get_colour_ref(colour):
    value = wx.Colour(colour)
    return (value.Blue() << 16) | (value.Green() << 8) | value.Red()


def apply_titlebar_theme(window, theme):
    try:
        handle = wintypes.HWND(window.GetHandle())
        value = ctypes.c_int(1 if theme['titlebar_dark'] else 0)
        for attribute in (DWMWA_USE_IMMERSIVE_DARK_MODE,
                          DWMWA_USE_IMMERSIVE_DARK_MODE_BEFORE_20H1):
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                handle, attribute, ctypes.byref(value), ctypes.sizeof(value))

        value = ctypes.c_int(get_colour_ref(theme['bg']))
        for attribute in (DWMWA_CAPTION_COLOR, DWMWA_BORDER_COLOR):
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                handle, attribute, ctypes.byref(value), ctypes.sizeof(value))
    except Exception:
        return

    # a shown frame repaints its DWM frame only after a resize
    if window.IsShown():
        width, height = window.GetSize()
        window.SetSize(width, height + 1)
        window.SetSize(width, height)


def apply_no_caption(window):
    # wxWidgets 3.3 keeps WS_CAPTION even when wxCAPTION is left out
    try:
        handle = wintypes.HWND(window.GetHandle())
        style = ctypes.windll.user32.GetWindowLongW(handle, GWL_STYLE)
        ctypes.windll.user32.SetWindowLongW(handle, GWL_STYLE, style & ~WS_CAPTION)
        ctypes.windll.user32.SetWindowPos(handle, 0, 0, 0, 0, 0,
                                          SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER |
                                          SWP_NOACTIVATE | SWP_FRAMECHANGED)
    except Exception:
        pass


def apply_clip_siblings(window):
    # wx gives children no WS_CLIPSIBLINGS, so a sibling repaint wipes floating windows
    try:
        handle = wintypes.HWND(window.GetHandle())
        style = ctypes.windll.user32.GetWindowLongW(handle, GWL_STYLE)
        ctypes.windll.user32.SetWindowLongW(handle, GWL_STYLE, style | WS_CLIPSIBLINGS)
    except Exception:
        pass


def allow_drop_messages(hwnd):
    try:
        user32 = ctypes.windll.user32
        if hasattr(user32, 'ChangeWindowMessageFilterEx'):
            user32.ChangeWindowMessageFilterEx.argtypes = [
                wintypes.HWND, wintypes.UINT, wintypes.DWORD, ctypes.c_void_p
            ]
            user32.ChangeWindowMessageFilterEx.restype = wintypes.BOOL
            for msg in (WM_DROPFILES, WM_COPYDATA, WM_COPYGLOBALDATA):
                user32.ChangeWindowMessageFilterEx(hwnd, msg, MSGFLT_ALLOW, None)
        elif hasattr(user32, 'ChangeWindowMessageFilter'):
            user32.ChangeWindowMessageFilter.argtypes = [wintypes.UINT, wintypes.DWORD]
            user32.ChangeWindowMessageFilter.restype = wintypes.BOOL
            for msg in (WM_DROPFILES, WM_COPYDATA, WM_COPYGLOBALDATA):
                user32.ChangeWindowMessageFilter(msg, MSGFLT_ALLOW)
    except Exception:
        pass


def enable_drop_target(window, on_drop):
    try:
        allow_drop_messages(wintypes.HWND(window.GetHandle()))
        window.DragAcceptFiles(True)
        window.Bind(wx.EVT_DROP_FILES, on_drop)
    except Exception:
        pass

    for child in window.GetChildren():
        enable_drop_target(child, on_drop)



def paint_now(window):
    # WM_PAINT is only generated once the queue is empty, which a moving mouse never lets happen
    try:
        ctypes.windll.user32.RedrawWindow(wintypes.HWND(window.GetHandle()), None, None,
                                          RDW_UPDATENOW | RDW_ALLCHILDREN)
    except Exception:
        pass


def call_painted(window, function, *args):
    def run():
        function(*args)
        if window:
            paint_now(window)
    wx.CallAfter(run)


def get_frame_margins(window):
    rect = WindowRect()
    try:
        if ctypes.windll.dwmapi.DwmGetWindowAttribute(
                wintypes.HWND(window.GetHandle()), DWMWA_EXTENDED_FRAME_BOUNDS,
                ctypes.byref(rect), ctypes.sizeof(rect)) != 0:
            return (0, 0, 0, 0)
    except Exception:
        return (0, 0, 0, 0)

    outer = window.GetScreenRect()
    return (rect.left - outer.x, rect.top - outer.y,
            outer.x + outer.width - rect.right, outer.y + outer.height - rect.bottom)


# file writes run on one asyncio loop in a daemon thread and hand nothing back to wx
LOOP = None
JOBS = {}


def run_async(coroutine):
    global LOOP
    if LOOP is None:
        LOOP = asyncio.new_event_loop()
        threading.Thread(target=LOOP.run_forever, name='async', daemon=True).start()
    return asyncio.run_coroutine_threadsafe(coroutine, LOOP)


def run_latest(key, coroutine):
    # a newer job of the same key cancels the older, so the last write wins
    job = JOBS.get(key)
    if job is not None:
        job.cancel()
    job = JOBS[key] = run_async(coroutine)
    return job


def cancel_job(key):
    job = JOBS.pop(key, None)
    if job is not None:
        job.cancel()
        # the loop runs its callbacks in order: once this returns the cancelled job is done
        run_async(asyncio.sleep(0)).result(timeout=2)


def finish_jobs(timeout=2.0):
    for job in list(JOBS.values()):
        try:
            job.result(timeout=timeout)
        except Exception:
            pass


def get_asset_path(*parts):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, 'assets', *parts)


def get_settings_path():
    return os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')),
                        APP_NAME, 'settings.json')


def load_settings():
    try:
        with open(get_settings_path(), encoding='utf-8') as file:
            return json.load(file)
    except Exception:
        return {}


def save_settings(settings):
    path = get_settings_path()
    return run_latest(path, write_settings(path, json.dumps(settings, ensure_ascii=False, indent=2)))


async def write_settings(path, text):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as file:
            file.write(text)
    except Exception:
        pass


def mix(colour, other, ratio):
    first, second = wx.Colour(colour), wx.Colour(other)
    return wx.Colour(*[round(a + (b - a) * ratio) for a, b in
                       ((first.Red(), second.Red()),
                        (first.Green(), second.Green()),
                        (first.Blue(), second.Blue()))])


def shade(colour, factor):
    base = wx.Colour(colour)
    return wx.Colour(min(255, int(base.Red() * factor)),
                     min(255, int(base.Green() * factor)),
                     min(255, int(base.Blue() * factor)))


def draw_card_rim(gc, colour, x, y, width, height, radius=CARD_RADIUS):
    # a pen draws the left and top edges thicker, so fill between two outlines
    path = gc.CreatePath()
    path.AddRoundedRectangle(x, y, width, height, radius)
    path.AddRoundedRectangle(x + 1, y + 1, width - 2, height - 2, max(0, radius - 1))
    gc.SetPen(wx.TRANSPARENT_PEN)
    gc.SetBrush(wx.Brush(wx.Colour(colour)))
    gc.FillPath(path, wx.ODDEVEN_RULE)


def get_font(size, bold=False):
    weight = wx.FONTWEIGHT_BOLD if bold else wx.FONTWEIGHT_NORMAL
    return wx.Font(size, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL,
                   weight, faceName='Segoe UI')


class Canvas(wx.Panel):

    def __init__(self, parent, theme):
        super().__init__(parent, style=wx.FULL_REPAINT_ON_RESIZE)
        self.theme = theme
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.SetDoubleBuffered(True)
        self.Bind(wx.EVT_PAINT, self.on_paint)
        self.Bind(wx.EVT_ERASE_BACKGROUND, lambda event: None)

    def set_theme(self, theme):
        self.theme = theme
        self.Refresh()

    def on_paint(self, event):
        dc = wx.AutoBufferedPaintDC(self)
        dc.SetBackground(wx.Brush(wx.Colour(self.theme['bg'])))
        dc.Clear()
        gc = wx.GraphicsContext.Create(dc)
        if gc is None:
            return
        gc.SetAntialiasMode(wx.ANTIALIAS_DEFAULT)
        width, height = self.GetClientSize()
        self.draw(gc, width, height)

    def draw(self, gc, width, height):
        pass

    def fit_text(self, gc, text, limit):
        if gc.GetTextExtent(text)[0] <= limit:
            return text
        while text and gc.GetTextExtent(text + '…')[0] > limit:
            text = text[:-1]
        return text + '…'

    def fit_tail(self, gc, text, limit):
        if gc.GetTextExtent(text)[0] <= limit:
            return text
        while text and gc.GetTextExtent('…' + text)[0] > limit:
            text = text[1:]
        return '…' + text
