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


RACK = {
    'bg': '#111214',
    'rail': '#24262a',
    'rail_edge': '#33363b',
    'hole': '#08090a',
    'screw': '#8f959d',
    'screw_dark': '#4a4e54',
    'text': '#e9ecef',
    'dim': '#9aa1aa',
    'faint': '#5f656d',
    'shadow': '#000000',
    'lcd': '#0b141c',
    'lcd_rim': '#05080b',
    'lcd_grid': '#182a39',
    'lcd_axis': '#25425a',
    'lcd_text': '#6f9fc6',
    'knob': '#3a3e45',
    'knob_top': '#5a5f67',
    'knob_edge': '#141518',
    'track': '#17191c',
    'led_off': '#2b2e33',
    'button': '#363a41',
    'button_hover': '#454a52',
    'button_down': '#2c2f35',
    'warn': '#e0a458',
}

# 장치마다 다른 판 색과 눈금 색. 색은 꾸밈이고 무엇인지는 언제나 이름이 말한다.
# 저자가 적녹색약이라 초록은 쓰지 않는다 — 파랑과 주황이 갈리는 축이다.
FACES = {
    'master': ('#2a2d32', '#4c9aff'),
    'preamp': ('#30343a', '#dfe4ea'),
    'parametric': ('#1f3347', '#5aa9ff'),
    'graphic': ('#2b3240', '#7cc4ff'),
    'delay': ('#3b3224', '#ffb04d'),
    'stereo': ('#302a3d', '#b7a3ff'),
    'vst': ('#1c1e22', '#ffb04d'),
    'custom': ('#2a2b2e', '#9aa1aa'),
}

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
    if engraved:
        set_font(gc, size, RACK['shadow'], bold)
        gc.DrawText(text, x, y + 1)
        set_font(gc, size, colour, bold)
    gc.DrawText(text, x, y)
    return width, height


def fit_text(gc, text, limit):
    if gc.GetTextExtent(text)[0] <= limit:
        return text
    while text and gc.GetTextExtent(text + '…')[0] > limit:
        text = text[:-1]
    return text + '…'


def fill_rect(gc, colour, x, y, width, height, radius=0):
    gc.SetPen(wx.TRANSPARENT_PEN)
    gc.SetBrush(wx.Brush(wx.Colour(colour)))
    if radius:
        gc.DrawRoundedRectangle(x, y, width, height, radius)
    else:
        gc.DrawRectangle(x, y, width, height)


def draw_screw(gc, cx, cy, radius=4.5):
    gc.SetPen(wx.TRANSPARENT_PEN)
    gc.SetBrush(gc.CreateRadialGradientBrush(
        cx - radius * 0.4, cy - radius * 0.4, cx, cy, radius * 1.3,
        wx.Colour('#c4c9cf'), wx.Colour(RACK['screw_dark'])))
    gc.DrawEllipse(cx - radius, cy - radius, radius * 2, radius * 2)
    gc.SetPen(get_pen(gc, '#2a2d31', 1.4))
    arm = radius * 0.62
    gc.StrokeLine(cx - arm, cy - arm * 0.35, cx + arm, cy + arm * 0.35)


def draw_rails(gc, x, y, width, height, ear):
    '''랙 양옆 기둥. 나사 구멍은 1U 마다 셋 — 실제 랙과 같은 박자다.'''
    for left in (x, x + width - ear):
        fill_rect(gc, RACK['rail'], left, y, ear, height)
        fill_rect(gc, RACK['rail_edge'], left + (ear - 1 if left == x else 0), y, 1, height)
        hole = 6
        step = 13.33
        top = y + 4
        while top < y + height - hole:
            fill_rect(gc, RACK['hole'], left + (ear - hole) / 2, top, hole, hole, 1)
            top += step


def draw_faceplate(gc, x, y, width, height, face, ear):
    '''장치 앞판. 위 가장자리는 빛을 받고 아래는 그늘이 진다. 귀에는 나사 둘씩.'''
    top, bottom = mix(face, '#ffffff', 0.10), mix(face, '#000000', 0.18)
    gc.SetPen(wx.TRANSPARENT_PEN)
    gc.SetBrush(gc.CreateLinearGradientBrush(x, y, x, y + height,
                                             wx.Colour(top), wx.Colour(bottom)))
    gc.DrawRectangle(x, y, width, height)
    fill_rect(gc, mix(face, '#ffffff', 0.28), x, y, width, 1)
    fill_rect(gc, mix(face, '#000000', 0.55), x, y + height - 1, width, 1)
    # 귀와 판 사이의 접힌 금.
    for left in (x + ear, x + width - ear - 1):
        fill_rect(gc, mix(face, '#000000', 0.35), left, y + 1, 1, height - 2)

    screws = (y + 10, y + height - 10) if height > 40 else (y + height / 2,)
    for cy in screws:
        draw_screw(gc, x + ear / 2, cy)
        draw_screw(gc, x + width - ear / 2, cy)


def draw_led(gc, cx, cy, on, colour, radius=5.5):
    gc.SetPen(wx.TRANSPARENT_PEN)
    if on:
        glow = wx.Colour(colour)
        gc.SetBrush(gc.CreateRadialGradientBrush(
            cx, cy, cx, cy, radius * 2.6,
            wx.Colour(glow.Red(), glow.Green(), glow.Blue(), 90),
            wx.Colour(glow.Red(), glow.Green(), glow.Blue(), 0)))
        gc.DrawEllipse(cx - radius * 2.6, cy - radius * 2.6, radius * 5.2, radius * 5.2)
        gc.SetBrush(gc.CreateRadialGradientBrush(
            cx - radius * 0.3, cy - radius * 0.3, cx, cy, radius,
            wx.Colour(mix(colour, '#ffffff', 0.6)), wx.Colour(colour)))
    else:
        gc.SetBrush(wx.Brush(wx.Colour(RACK['led_off'])))
    gc.DrawEllipse(cx - radius, cy - radius, radius * 2, radius * 2)
    gc.SetPen(get_pen(gc, '#0c0d0f', 1))
    gc.SetBrush(wx.TRANSPARENT_BRUSH)
    gc.DrawEllipse(cx - radius, cy - radius, radius * 2, radius * 2)


def draw_lcd(gc, rect):
    fill_rect(gc, RACK['lcd_rim'], rect.x - 2, rect.y - 2, rect.width + 4, rect.height + 4, 4)
    fill_rect(gc, RACK['lcd'], rect.x, rect.y, rect.width, rect.height, 3)


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
                 bipolar=False, step=None):
        super().__init__()
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

    def draw(self, gc, accent):
        rect = self.rect
        cx = rect.x + rect.width / 2
        radius = min(rect.width / 2 - 4, 15)
        # 플러그인 파라미터 이름은 길이를 플러그인이 정한다. 옆 손잡이에 닿기 전에 자른다.
        set_font(gc, 7.5, RACK['dim'])
        label = fit_text(gc, self.label, rect.width - 2)
        draw_text(gc, label, cx, rect.y, 7.5, RACK['dim'], align='center', engraved=True)
        cy = rect.y + 14 + radius + 2

        ratio = self.to_ratio(self.get()) if self.enabled else 0.0
        track = radius + 3
        gc.SetPen(gc.CreatePen(wx.GraphicsPenInfo(wx.Colour(RACK['track'])).Width(3)
                               .Cap(wx.CAP_ROUND)))
        gc.SetBrush(wx.TRANSPARENT_BRUSH)
        gc.StrokePath(get_arc(gc, cx, cy, track, KNOB_START, KNOB_START + KNOB_SWEEP))
        if self.enabled:
            origin = KNOB_START + KNOB_SWEEP * (0.5 if self.bipolar else 0.0)
            angle = KNOB_START + KNOB_SWEEP * ratio
            if abs(angle - origin) > 0.01:
                gc.SetPen(gc.CreatePen(wx.GraphicsPenInfo(wx.Colour(accent)).Width(3)
                                       .Cap(wx.CAP_ROUND)))
                gc.StrokePath(get_arc(gc, cx, cy, track, origin, angle))

        body = radius - 1
        gc.SetPen(get_pen(gc, RACK['knob_edge'], 1))
        gc.SetBrush(gc.CreateRadialGradientBrush(
            cx - body * 0.35, cy - body * 0.45, cx, cy, body * 1.25,
            wx.Colour(RACK['knob_top']), wx.Colour(RACK['knob'])))
        gc.DrawEllipse(cx - body, cy - body, body * 2, body * 2)
        if self.hovered or self.pressed:
            gc.SetPen(get_pen(gc, mix(RACK['knob_top'], '#ffffff', 0.3), 1))
            gc.SetBrush(wx.TRANSPARENT_BRUSH)
            gc.DrawEllipse(cx - body, cy - body, body * 2, body * 2)

        angle = KNOB_START + KNOB_SWEEP * ratio
        gc.SetPen(gc.CreatePen(wx.GraphicsPenInfo(
            wx.Colour('#f2f4f6' if self.enabled else RACK['faint'])).Width(2)
            .Cap(wx.CAP_ROUND)))
        gc.StrokeLine(cx + math.cos(angle) * body * 0.30, cy + math.sin(angle) * body * 0.30,
                      cx + math.cos(angle) * body * 0.82, cy + math.sin(angle) * body * 0.82)

        value = self.text(self.get()) if self.enabled else '—'
        draw_text(gc, value, cx, cy + radius + 5, 7.5,
                  RACK['text'] if self.enabled else RACK['faint'], align='center')


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
        fill_rect(gc, RACK['track'], cx - 2, top, 4, bottom - top, 2)
        zero = self.to_y(0)
        y = self.to_y(self.get())
        fill_rect(gc, accent, cx - 2, min(zero, y), 4, abs(zero - y), 1)

        width, height = self.THUMB
        fill = RACK['knob_top'] if (self.hovered or self.pressed) else RACK['knob']
        gc.SetPen(get_pen(gc, RACK['knob_edge'], 1))
        gc.SetBrush(wx.Brush(wx.Colour(fill)))
        gc.DrawRoundedRectangle(cx - width / 2, y - height / 2, width, height, 2)
        fill_rect(gc, '#f2f4f6', cx - width / 2 + 2, y - 0.5, width - 4, 1)

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
        gc.SetPen(get_pen(gc, '#0c0d0f', 1))
        gc.SetBrush(wx.Brush(wx.Colour(fill)))
        gc.DrawRoundedRectangle(rect.x + 0.5, rect.y + 0.5, rect.width - 1, rect.height - 1, 4)
        if not lit:
            fill_rect(gc, mix(fill, '#ffffff', 0.10), rect.x + 2, rect.y + 1, rect.width - 4, 1)
        caption = self.confirm if self.asking is not None else self.caption
        colour = '#101215' if lit else (RACK['warn'] if self.asking is not None else
                                        RACK['text'] if self.enabled else RACK['faint'])
        set_font(gc, 8.5, colour)
        caption = fit_text(gc, caption, rect.width - 8)
        width, height = gc.GetTextExtent(caption)[:2]
        gc.DrawText(caption, rect.x + (rect.width - width) / 2,
                    rect.y + (rect.height - height) / 2)


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
            colour = RACK['faint']
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
            gc.SetPen(get_pen(gc, '#0c0d0f', 1))
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
