# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com

랙에 꽂히는 장치들이 함께 쓰는 그림과 조작부. 위젯을 쓰지 않고 랙 캔버스 한 장에
모두 그린다 — 장치 수십 개가 한 화면에 있어도 창은 하나다.

조작부는 제 자리(rect)만 안다. 누름·끌기·두 번 누름은 랙이 골라 넘겨준다.
움직임은 넣지 않는다. 값이 바뀌면 그 자리에서 곧장 다시 그린다.
'''


import math
import wx

from utilities import mix


# Native Instruments 식 평평한 숯색 판. 회색은 색을 띠지 않고, 강조는 장치 색 하나뿐이다.
RACK = {
    'bg': '#111214',
    'panel': '#1d1f23',
    'band': '#17181b',
    'line': '#2b2e33',
    'text': '#e6e7e9',
    'dim': '#8b8f96',
    'faint': '#5a5e65',
    'shadow': '#000000',
    'lcd': '#111215',
    'lcd_rim': '#2b2e33',
    'lcd_grid': '#1e2126',
    'lcd_axis': '#343840',
    'lcd_text': '#7d828a',
    'knob': '#2a2d32',
    'knob_top': '#33363c',
    'knob_edge': '#3d4148',
    'track': '#2c2f35',
    'led_off': '#3a3d43',
    'button': '#26282d',
    'button_hover': '#2f3237',
    'button_down': '#202226',
    'button_edge': '#363940',
    'warn': '#ff9a3d',
}

# 장치마다 다른 판 색과 눈금 색. 색은 꾸밈이고 무엇인지는 언제나 이름이 말한다.
# 저자가 적녹색약이라 초록은 쓰지 않는다 — 파랑과 주황이 갈리는 축이다.
FACES = {
    'master': ('#1d1f23', '#3d9bff'),
    'preamp': ('#1d1f23', '#c9ccd1'),
    'parametric': ('#1d1f23', '#3d9bff'),
    'graphic': ('#1d1f23', '#62b2ff'),
    'delay': ('#1d1f23', '#ff9a3d'),
    'stereo': ('#1d1f23', '#a894ff'),
    'vst': ('#1d1f23', '#ff9a3d'),
    'leveler': ('#1d1f23', '#7fb8ff'),
    'custom': ('#1d1f23', '#8b8f96'),
}

# 모든 판의 이름 띠 높이. 접은 장치는 이 띠만 남는다.
HEADER_BAND = 30
TITLE_SIZE = 9
KNOB_RADIUS = 14
LABEL_HEIGHT = 11
# 이름 글씨와 값 호 사이. 5 는 너무 붙어 보였다(사용자).
LABEL_GAP = 8
KNOB_SWEEP = math.radians(270)
KNOB_START = math.radians(135)
DRAG_RANGE = 180.0
FINE = 10.0


FONTS = {}


def get_font(size, bold=False):
    '''랙 글씨는 반 포인트 단위로 고른다. wx.Font 생성자는 정수만 받아 FontInfo 로 만든다.'''
    key = (size, bold)
    if key not in FONTS:
        info = wx.FontInfo(size).FaceName('Segoe UI')
        FONTS[key] = wx.Font(info.Bold() if bold else info)
    return FONTS[key]


def get_pen(gc, colour, width):
    '''wx.Pen 은 정수 굵기만 받는다. 반 칸 굵기는 그래픽 펜으로.'''
    return gc.CreatePen(wx.GraphicsPenInfo(wx.Colour(colour)).Width(width))


def set_font(gc, size, colour, bold=False):
    gc.SetFont(get_font(size, bold), wx.Colour(colour))


def draw_text(gc, text, x, y, size, colour, bold=False, align='left', engraved=False):
    '''판에 새긴 글씨는 아래로 한 칸 검은 그림자를 깐다.'''
    set_font(gc, size, colour, bold)
    width, height = gc.GetTextExtent(text)[:2]
    if align == 'center':
        x -= width / 2
    elif align == 'right':
        x -= width
    # 판이 평평하니 새긴 글씨의 그림자도 없다. engraved 는 옛 부름을 받아 주기만 한다.
    gc.DrawText(text, x, y)
    return width, height


def fit_text(gc, text, limit):
    if gc.GetTextExtent(text)[0] <= limit:
        return text
    while text and gc.GetTextExtent(text + '…')[0] > limit:
        text = text[:-1]
    return text + '…'


LABEL_SIZE = 7.5
LABEL_SMALL = 6.5


def fit_label(gc, text, limit):
    '''손잡이 이름: 7.5 로 안 들어가면 6.5 로 줄여 보고, 그래도 넘치면 그때 자른다.
    'WIDE AMOUNT', 'ISP DETECTION' 이 잘려 읽히지 않았다(사용자).'''
    for size in (LABEL_SIZE, LABEL_SMALL):
        set_font(gc, size, RACK['dim'])
        if gc.GetTextExtent(text)[0] <= limit:
            return text, size
    return fit_text(gc, text, limit), LABEL_SMALL


def fill_rect(gc, colour, x, y, width, height, radius=0):
    gc.SetPen(wx.TRANSPARENT_PEN)
    gc.SetBrush(wx.Brush(wx.Colour(colour)))
    if radius:
        gc.DrawRoundedRectangle(x, y, width, height, radius)
    else:
        gc.DrawRectangle(x, y, width, height)


def draw_rails(gc, x, y, width, height, ear):
    '''레일은 없다(NI 식 평평한 랙). 판 뒤 바닥만 칠한다.'''
    fill_rect(gc, RACK['bg'], x, y, width, height)


def draw_faceplate(gc, x, y, width, height, face, ear, accent=None):
    '''장치 판. 평평한 숯색 본체 위에 한 톤 어두운 이름 띠, 띠 아래 1 px 선. 장치 색은 띠
    왼쪽 끝의 가는 줄에만 쓴다. 띠는 판 키와 상관없이 같아 접어도 그대로 보인다.'''
    fill_rect(gc, RACK['panel'], x, y, width, height, 3)
    band = min(height, HEADER_BAND)
    fill_rect(gc, RACK['band'], x, y, width, band, 3)
    if height > HEADER_BAND:
        fill_rect(gc, RACK['band'], x, y + band - 3, width, 3)
        fill_rect(gc, RACK['line'], x, y + HEADER_BAND, width, 1)
    if accent:
        fill_rect(gc, accent, x, y + 6, 2, band - 12, 1)


def draw_title(gc, left, y, title, subtitle, tone, limit):
    '''이름 띠의 제목과 부제. 모든 판이 같은 크기·같은 자리에 쓴다 — 접어도 그대로다.'''
    middle = y + HEADER_BAND / 2
    set_font(gc, TITLE_SIZE, RACK['text'], bold=True)
    title = fit_text(gc, title.upper(), limit)
    # 제목은 굵게, 부제는 흐리게 — NI 처럼 대문자 제목 한 줄.
    width = draw_text(gc, title, left, middle - 8, TITLE_SIZE, RACK['text'], bold=True,
                      engraved=True)[0]
    if subtitle:
        set_font(gc, 8, tone)
        subtitle = fit_text(gc, subtitle, max(0, limit - width - 12))
        draw_text(gc, subtitle, left + width + 12, middle - 6, 8, tone, engraved=True)
    return width


# 이름 띠의 구역 토글 칩(Analyzer 의 METERS·SPECTRUM, Leveler 의 METERS·CONTROLS). 모양은 여기 하나.
CHIP_HEIGHT = 16
CHIP_PAD = 6
CHIP_GAP = 4
CHIP_TEXT = 6.5
CHIP_LIT = FACES['master'][1]


def get_chip_width(gc, text):
    set_font(gc, CHIP_TEXT, RACK['text'], bold=True)
    return int(math.ceil(gc.GetTextExtent(text.upper())[0])) + CHIP_PAD * 2


def draw_chip(gc, rect, text, lit):
    '''평평한 글씨 칩. 켜져 있으면 CHIP_LIT, 꺼져 있으면 테두리만. 판 색을 따르지 않는다 —
    Analyzer·Leveler 칩 색이 달라 보였다(사용자).'''
    fill = CHIP_LIT if lit else RACK['button']
    gc.SetPen(get_pen(gc, fill if lit else RACK['button_edge'], 1))
    gc.SetBrush(wx.Brush(wx.Colour(fill)))
    gc.DrawRoundedRectangle(rect.x + 0.5, rect.y + 0.5, rect.width - 1, rect.height - 1, 3)
    draw_text(gc, text.upper(), rect.x + rect.width / 2, rect.y + rect.height / 2 - 5.5, CHIP_TEXT,
              '#101215' if lit else RACK['dim'], bold=True, align='center')


def draw_led(gc, cx, cy, on, colour, radius=5.5):
    '''켜고 끄기. LED 대신 전원 기호 — 켜지면 장치 색, 꺼지면 흐린 회색.'''
    tone = colour if on else RACK['led_off']
    gc.SetPen(gc.CreatePen(wx.GraphicsPenInfo(wx.Colour(tone)).Width(1.6).Cap(wx.CAP_ROUND)))
    gc.SetBrush(wx.TRANSPARENT_BRUSH)
    arc = gc.CreatePath()
    arc.AddArc(cx, cy + 0.5, radius, math.radians(-60), math.radians(240), True)
    gc.StrokePath(arc)
    gc.StrokeLine(cx, cy - radius - 0.5, cx, cy - 1)


def draw_lcd(gc, rect):
    '''화면. 평평한 검은 판에 1 px 테두리.'''
    fill_rect(gc, RACK['lcd_rim'], rect.x - 1, rect.y - 1, rect.width + 2, rect.height + 2, 3)
    fill_rect(gc, RACK['lcd'], rect.x, rect.y, rect.width, rect.height, 2)


def get_arc(gc, cx, cy, radius, start, end):
    path = gc.CreatePath()
    if end < start:
        start, end = end, start
    path.AddArc(cx, cy, radius, start, end, True)
    return path


def draw_glyph(gc, name, cx, cy, size, colour):
    gc.SetPen(gc.CreatePen(wx.GraphicsPenInfo(wx.Colour(colour)).Width(1.5)
                           .Cap(wx.CAP_ROUND).Join(wx.JOIN_ROUND)))
    gc.SetBrush(wx.TRANSPARENT_BRUSH)
    half = size / 2
    if name == 'up' or name == 'down':
        sign = -1 if name == 'up' else 1
        path = gc.CreatePath()
        path.MoveToPoint(cx - half * 0.7, cy - sign * half * 0.35)
        path.AddLineToPoint(cx, cy + sign * half * 0.35)
        path.AddLineToPoint(cx + half * 0.7, cy - sign * half * 0.35)
        gc.StrokePath(path)
    elif name == 'left' or name == 'right':
        sign = -1 if name == 'left' else 1
        path = gc.CreatePath()
        path.MoveToPoint(cx - sign * half * 0.35, cy - half * 0.7)
        path.AddLineToPoint(cx + sign * half * 0.35, cy)
        path.AddLineToPoint(cx - sign * half * 0.35, cy + half * 0.7)
        gc.StrokePath(path)
    elif name == 'close':
        arm = half * 0.6
        gc.StrokeLine(cx - arm, cy - arm, cx + arm, cy + arm)
        gc.StrokeLine(cx - arm, cy + arm, cx + arm, cy - arm)
    elif name == 'plus':
        arm = half * 0.7
        gc.StrokeLine(cx - arm, cy, cx + arm, cy)
        gc.StrokeLine(cx, cy - arm, cx, cy + arm)


# ---------------------------------------------------------------- 조작부


class Control:

    cursor = wx.CURSOR_HAND
    enabled = True
    tip = ''

    def __init__(self):
        self.rect = wx.Rect()
        self.hovered = False
        self.pressed = False

    def contains(self, point):
        return self.enabled and self.rect.Contains(point)

    def on_down(self, point, shift):
        self.pressed = True

    def on_drag(self, point, shift):
        pass

    def on_up(self, point):
        clicked = self.pressed and self.rect.Contains(point)
        self.pressed = False
        if clicked:
            self.on_click()

    def on_click(self):
        pass

    def on_dclick(self, point):
        pass

    def draw(self, gc, accent):
        pass


class Knob(Control):
    '''위아래로 끌어 돌린다. Shift 를 누르면 열 배 곱게, 두 번 누르면 기본값.'''

    cursor = wx.CURSOR_SIZENS

    def __init__(self, label, get, put, low, high, default, text, log=False,
                 bipolar=False, step=None, ends=None):
        super().__init__()
        # 값 호 양 끝 아래의 최소·최대 글씨(Harrison 콘솔처럼). 없으면 쓰지 않는다.
        self.ends = ends
        self.label = label
        self.get = get
        self.put = put
        self.low, self.high = low, high
        self.default = default
        self.text = text
        self.log = log
        self.bipolar = bipolar
        self.step = step
        self.origin = None

    def to_ratio(self, value):
        value = min(max(value, self.low), self.high)
        if self.log:
            return math.log(value / self.low) / math.log(self.high / self.low)
        return (value - self.low) / (self.high - self.low)

    def from_ratio(self, ratio):
        ratio = min(max(ratio, 0.0), 1.0)
        if self.log:
            value = self.low * math.exp(math.log(self.high / self.low) * ratio)
        else:
            value = self.low + (self.high - self.low) * ratio
        if self.step:
            value = round(value / self.step) * self.step
        return value

    def on_down(self, point, shift):
        super().on_down(point, shift)
        self.origin = (point.y, self.to_ratio(self.get()), shift)

    def on_drag(self, point, shift):
        if self.origin is None:
            return
        top, ratio, fine = self.origin
        # Shift 를 끌기 도중에 누르거나 떼도 손잡이가 튀지 않게 그 자리에서 다시 잡는다.
        if shift != fine:
            self.origin = (point.y, self.to_ratio(self.get()), shift)
            return
        span = DRAG_RANGE * (FINE if shift else 1)
        self.put(self.from_ratio(ratio + (top - point.y) / span))

    def on_up(self, point):
        self.pressed = False
        self.origin = None

    def on_dclick(self, point):
        self.put(self.default)

    def get_reach(self, gc, width):
        '''가운데에서 보이는 왼쪽 끝까지. 값 글씨는 바뀌어 넣지 않는다(놓인 자리가 춤춘다).'''
        radius = min(width / 2 - 4, KNOB_RADIUS)
        track = radius + 3
        reach = track + 1.5
        set_font(gc, 7.5, RACK['dim'])
        label, size = fit_label(gc, self.label, width - 2)
        set_font(gc, size, RACK['dim'])
        reach = max(reach, gc.GetTextExtent(label)[0] / 2)
        if self.ends:
            set_font(gc, 6, RACK['faint'])
            reach = max(reach, -math.cos(KNOB_START) * (track + 2) + 1 +
                        gc.GetTextExtent(self.ends[0])[0])
        return reach

    def draw(self, gc, accent):
        rect = self.rect
        cx = rect.x + rect.width / 2
        radius = min(rect.width / 2 - 4, KNOB_RADIUS)
        # 플러그인 파라미터 이름은 길이를 플러그인이 정한다. 옆 손잡이에 닿기 전에 자른다.
        label, size = fit_label(gc, self.label, rect.width - 2)
        draw_text(gc, label, cx, rect.y + (LABEL_SIZE - size), size, RACK['dim'], align='center',
                  engraved=True)
        # 이름 글씨 아래로 값 호의 바깥 끝까지 LABEL_GAP 을 띄운다. 호는 반지름 + 3 에 3 화소 굵기.
        cy = rect.y + LABEL_HEIGHT + LABEL_GAP + radius + 4.5

        ratio = self.to_ratio(self.get()) if self.enabled else 0.0
        track = radius + 3
        gc.SetPen(gc.CreatePen(wx.GraphicsPenInfo(wx.Colour(RACK['track'])).Width(2.5)
                               .Cap(wx.CAP_BUTT)))
        gc.SetBrush(wx.TRANSPARENT_BRUSH)
        gc.StrokePath(get_arc(gc, cx, cy, track, KNOB_START, KNOB_START + KNOB_SWEEP))
        if self.enabled:
            origin = KNOB_START + KNOB_SWEEP * (0.5 if self.bipolar else 0.0)
            angle = KNOB_START + KNOB_SWEEP * ratio
            if abs(angle - origin) > 0.01:
                gc.SetPen(gc.CreatePen(wx.GraphicsPenInfo(wx.Colour(accent)).Width(2.5)
                                       .Cap(wx.CAP_BUTT)))
                gc.StrokePath(get_arc(gc, cx, cy, track, origin, angle))

        # 몸통은 평평한 원판 하나. 손이 얹히면 테두리만 밝아진다.
        body = radius - 2
        lit = self.hovered or self.pressed
        gc.SetPen(get_pen(gc, mix(RACK['knob_edge'], '#ffffff', 0.18) if lit else
                          RACK['knob_edge'], 1))
        gc.SetBrush(wx.Brush(wx.Colour(RACK['knob_top'] if lit else RACK['knob'])))
        gc.DrawEllipse(cx - body, cy - body, body * 2, body * 2)
        angle = KNOB_START + KNOB_SWEEP * ratio
        gc.SetPen(gc.CreatePen(wx.GraphicsPenInfo(
            wx.Colour(RACK['text'] if self.enabled else RACK['faint'])).Width(2)
            .Cap(wx.CAP_ROUND)))
        gc.StrokeLine(cx + math.cos(angle) * body * 0.20, cy + math.sin(angle) * body * 0.20,
                      cx + math.cos(angle) * body * 0.78, cy + math.sin(angle) * body * 0.78)

        if self.ends:
            for text, angle, align in ((self.ends[0], KNOB_START, 'right'),
                                       (self.ends[1], KNOB_START + KNOB_SWEEP, 'left')):
                x = cx + math.cos(angle) * (track + 2)
                y = cy + math.sin(angle) * (track + 2)
                draw_text(gc, text, x + (-1 if align == 'right' else 1), y - 3, 6, RACK['faint'],
                          align=align)
        value = self.text(self.get()) if self.enabled else '—'
        draw_text(gc, value, cx, cy + radius + 4, 7.5,
                  RACK['text'] if self.enabled else RACK['faint'], align='center')


class Switch(Control):
    '''켜고 끄는 값(플러그인의 ON/OFF 파라미터). 손잡이와 같은 칸에 같은 이름 줄, 손잡이
    자리에 글씨 단추 하나. 누를 때마다 0 과 1 을 오간다. 켜지면 장치 색.'''

    WIDTH = 40
    HEIGHT = 20

    def __init__(self, label, get, put, text):
        super().__init__()
        self.label = label
        self.get = get
        self.put = put
        self.text = text

    def is_on(self):
        return self.get() >= 0.5

    def get_reach(self, gc, width):
        set_font(gc, 7.5, RACK['dim'])
        text, size = fit_label(gc, self.label, width - 2)
        set_font(gc, size, RACK['dim'])
        label = gc.GetTextExtent(text)[0] / 2
        return max(label, self.WIDTH / 2)

    def get_button(self):
        rect = self.rect
        radius = min(rect.width / 2 - 4, KNOB_RADIUS)
        cy = rect.y + LABEL_HEIGHT + LABEL_GAP + radius + 4.5
        return wx.Rect(int(rect.x + (rect.width - self.WIDTH) / 2), int(cy - self.HEIGHT / 2),
                       self.WIDTH, self.HEIGHT)

    def on_click(self):
        self.put(0.0 if self.is_on() else 1.0)

    def on_dclick(self, point):
        # 빨리 두 번 누르면 두 번째 누름은 두 번 누름으로 온다. 그것도 한 번 누름이다.
        self.on_click()

    def draw(self, gc, accent):
        rect = self.rect
        cx = rect.x + rect.width / 2
        label, size = fit_label(gc, self.label, rect.width - 2)
        draw_text(gc, label, cx, rect.y + (LABEL_SIZE - size), size, RACK['dim'], align='center')
        button = self.get_button()
        on = self.is_on() and self.enabled
        lit = self.hovered or self.pressed
        fill = accent if on else RACK['button_hover'] if lit else RACK['button']
        gc.SetPen(get_pen(gc, fill if on else RACK['button_edge'], 1))
        gc.SetBrush(wx.Brush(wx.Colour(fill)))
        gc.DrawRoundedRectangle(button.x + 0.5, button.y + 0.5, button.width - 1,
                                button.height - 1, 3)
        text = (self.text(self.get()) or ('ON' if on else 'OFF')).strip().upper()
        set_font(gc, 7.5, RACK['text'], bold=True)
        text = fit_text(gc, text, button.width - 6)
        draw_text(gc, text, cx, button.y + 3.5, 7.5, '#101215' if on else RACK['dim'],
                  bold=True, align='center')


class Fader(Control):
    '''그래픽 EQ 의 세로 막대. 끌면 손잡이가 커서를 따라간다.'''

    cursor = wx.CURSOR_SIZENS
    THUMB = (14, 8)
    show_label = True

    def __init__(self, label, get, put, low, high, default, text):
        super().__init__()
        self.label = label
        self.get = get
        self.put = put
        self.low, self.high = low, high
        self.default = default
        self.text = text
        self.origin = None

    def get_slot(self):
        rect = self.rect
        return rect.y + 14, rect.y + rect.height - 16

    def to_y(self, value):
        top, bottom = self.get_slot()
        ratio = (min(max(value, self.low), self.high) - self.low) / (self.high - self.low)
        return bottom - (bottom - top) * ratio

    def on_down(self, point, shift):
        super().on_down(point, shift)
        self.origin = (point.y, self.get(), shift)

    def on_drag(self, point, shift):
        if self.origin is None:
            return
        top, value, fine = self.origin
        if shift != fine:
            self.origin = (point.y, self.get(), shift)
            return
        slot_top, slot_bottom = self.get_slot()
        per_pixel = (self.high - self.low) / max(1, slot_bottom - slot_top)
        if shift:
            per_pixel /= FINE
        value = value + (top - point.y) * per_pixel
        self.put(round(min(max(value, self.low), self.high) * 10) / 10)

    def on_up(self, point):
        self.pressed = False
        self.origin = None

    def on_dclick(self, point):
        self.put(self.default)

    def draw(self, gc, accent):
        rect = self.rect
        cx = rect.x + rect.width / 2
        top, bottom = self.get_slot()
        fill_rect(gc, RACK['track'], cx - 1, top, 2, bottom - top, 1)
        zero = self.to_y(0)
        y = self.to_y(self.get())
        fill_rect(gc, accent, cx - 1, min(zero, y), 2, abs(zero - y), 1)

        width, height = self.THUMB
        lit = self.hovered or self.pressed
        gc.SetPen(wx.TRANSPARENT_PEN)
        gc.SetBrush(wx.Brush(wx.Colour('#e6e7e9' if lit else '#c4c7cc')))
        gc.DrawRoundedRectangle(cx - width / 2, y - height / 2, width, height, 1.5)
        fill_rect(gc, '#2a2d32', cx - width / 2 + 2, y - 0.5, width - 4, 1)

        if self.hovered or self.pressed:
            draw_text(gc, self.text(self.get()), cx, rect.y, 7, RACK['text'], align='center')
        if self.show_label:
            draw_text(gc, self.label, cx, bottom + 4, 7, RACK['dim'], align='center',
                      engraved=True)


class Button(Control):
    '''글자 단추. confirm 을 주면 첫 누름에 물음으로 바뀌고 두 번째에 실행한다.'''

    HEIGHT = 22

    def __init__(self, caption, action, confirm=None, active=None):
        super().__init__()
        self.caption = caption
        self.action = action
        self.confirm = confirm
        self.active = active
        self.asking = None

    def get_width(self, gc):
        set_font(gc, 8.5, RACK['text'])
        widths = [gc.GetTextExtent(text)[0] for text in (self.caption, self.confirm) if text]
        return math.ceil(max(widths)) + 22

    def on_click(self):
        if self.confirm and self.asking is None:
            self.asking = wx.CallLater(4000, self.reset)
            return
        self.reset()
        self.action()

    def reset(self):
        if self.asking is not None:
            if self.asking.IsRunning():
                self.asking.Stop()
            self.asking = None
            if self.on_reset:
                self.on_reset()

    on_reset = None

    def draw(self, gc, accent):
        rect = self.rect
        lit = self.active() if self.active else False
        if not self.enabled:
            fill = mix(RACK['button'], RACK['bg'], 0.5)
        elif lit:
            fill = accent
        elif self.pressed:
            fill = RACK['button_down']
        elif self.hovered:
            fill = RACK['button_hover']
        else:
            fill = RACK['button']
        gc.SetPen(get_pen(gc, fill if lit else RACK['button_edge'], 1))
        gc.SetBrush(wx.Brush(wx.Colour(fill)))
        gc.DrawRoundedRectangle(rect.x + 0.5, rect.y + 0.5, rect.width - 1, rect.height - 1, 3)
        caption = self.confirm if self.asking is not None else self.caption
        colour = '#101215' if lit else (RACK['warn'] if self.asking is not None else
                                        RACK['text'] if self.enabled else RACK['faint'])
        set_font(gc, 8.5, colour)
        caption = fit_text(gc, caption, rect.width - 8)
        width, height = gc.GetTextExtent(caption)[:2]
        gc.DrawText(caption, rect.x + (rect.width - width) / 2,
                    rect.y + (rect.height - height) / 2)


class Chip(Control):
    '''이름 띠의 구역 토글. 누르면 action, active() 가 참이면 켜진 모양.'''

    def __init__(self, caption, action, active, tip=''):
        super().__init__()
        self.caption = caption
        self.action = action
        self.active = active
        self.tip = tip

    # Analyzer 의 칩과 같은 손맛: 누르는 순간 바뀌고, 빨리 두 번 눌러도 한 번(사용자: 일관성).
    def on_down(self, point, shift):
        self.action()

    def on_up(self, point):
        self.pressed = False

    def on_dclick(self, point):
        pass

    def draw(self, gc, accent):
        draw_chip(gc, self.rect, self.caption, self.active())


class IconButton(Button):
    '''장치 오른쪽 끝의 작은 단추. 위·아래로 옮기기와 빼기.'''

    SIZE = 18

    def __init__(self, glyph, action, confirm=None, tip=''):
        super().__init__('', action, confirm)
        self.glyph = glyph
        self.tip = tip

    def draw(self, gc, accent):
        rect = self.rect
        asking = self.asking is not None
        if asking:
            fill = RACK['warn']
        elif self.pressed:
            fill = RACK['button_down']
        elif self.hovered:
            fill = RACK['button_hover']
        else:
            fill = None
        if fill:
            fill_rect(gc, fill, rect.x, rect.y, rect.width, rect.height, 3)
        colour = '#101215' if asking else (RACK['text'] if self.hovered else RACK['dim'])
        if not self.enabled:
            # 더 갈 수 없는 쪽: 꺼진 불과 같은 어두운 회색.
            colour = RACK['led_off']
        draw_glyph(gc, self.glyph, rect.x + rect.width / 2, rect.y + rect.height / 2, 10,
                   colour)

    def contains(self, point):
        return self.rect.Contains(point) and self.enabled


class Power(Control):
    '''장치의 켜고 끄기. 불이 켜져 있으면 소리가 그 장치를 지난다.'''

    def __init__(self, get, put):
        super().__init__()
        self.get = get
        self.put = put

    def on_click(self):
        self.put(not self.get())

    def draw(self, gc, accent):
        rect = self.rect
        draw_led(gc, rect.x + rect.width / 2, rect.y + rect.height / 2, self.get(), accent)


class Segment(Control):
    '''선택지 몇 개를 한 줄(또는 한 칸씩 세로)로. 고른 것만 불이 켜진다.'''

    def __init__(self, options, get, put, vertical=False):
        super().__init__()
        self.options = options
        self.get = get
        self.put = put
        self.vertical = vertical
        self.hover_index = -1

    def get_cells(self):
        count = len(self.options)
        rect = self.rect
        cells = []
        for index in range(count):
            if self.vertical:
                height = rect.height / count
                cells.append(wx.Rect(rect.x, round(rect.y + height * index),
                                     rect.width, round(height) - 2))
            else:
                width = rect.width / count
                cells.append(wx.Rect(round(rect.x + width * index), rect.y,
                                     round(width) - 2, rect.height))
        return cells

    def get_index(self, point):
        for index, cell in enumerate(self.get_cells()):
            if cell.Contains(point):
                return index
        return -1

    def on_down(self, point, shift):
        super().on_down(point, shift)
        self.down_index = self.get_index(point)

    def on_up(self, point):
        self.pressed = False
        index = self.get_index(point)
        if index >= 0 and index == getattr(self, 'down_index', -1):
            self.put(self.options[index][0])

    def track(self, point):
        index = self.get_index(point) if self.rect.Contains(point) else -1
        changed = index != self.hover_index
        self.hover_index = index
        return changed

    def draw(self, gc, accent):
        current = self.get() if self.enabled else None
        for index, (cell, (value, caption)) in enumerate(zip(self.get_cells(), self.options)):
            lit = value == current
            if lit:
                fill = accent
            elif self.hovered and index == self.hover_index:
                fill = RACK['button_hover']
            else:
                fill = RACK['button']
            if not self.enabled:
                fill = mix(RACK['button'], RACK['bg'], 0.5)
            gc.SetPen(get_pen(gc, fill if lit else RACK['button_edge'], 1))
            gc.SetBrush(wx.Brush(wx.Colour(fill)))
            gc.DrawRoundedRectangle(cell.x + 0.5, cell.y + 0.5, cell.width - 1,
                                    cell.height - 1, 3)
            colour = '#101215' if lit else (RACK['text'] if self.enabled else RACK['faint'])
            set_font(gc, 8, colour, bold=lit)
            text = fit_text(gc, caption, cell.width - 6)
            width, height = gc.GetTextExtent(text)[:2]
            gc.DrawText(text, cell.x + (cell.width - width) / 2,
                        cell.y + (cell.height - height) / 2)


# ---------------------------------------------------------------- 값 글씨


def get_db_text(value):
    return '%+.1f dB' % value if abs(value) >= 0.05 else '0.0 dB'


def get_hz_text(value):
    if value >= 10000:
        return '%.1f kHz' % (value / 1000)
    if value >= 1000:
        return '%.2f kHz' % (value / 1000)
    return '%d Hz' % round(value)


def get_short_hz(value):
    if value >= 1000:
        text = ('%.1f' % (value / 1000)).rstrip('0').rstrip('.')
        return text + 'k'
    return '%d' % round(value)
