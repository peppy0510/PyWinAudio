# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com

랙에 꽂는 장치들. 값은 모두 data 사전 하나에 있고 그것이 곧 저장되는 모양이다 —
장치 객체는 그 사전을 그리고 만지는 손잡이일 뿐이다. 소리는 위에서 아래로 지난다.

키가 작은 장치(2U)는 이름판을 왼쪽에, 큰 장치는 위쪽 띠에 둔다.
'''


import copy
import math
import os
import wx

import dsp
import eapo

from rackui import FACES
from rackui import HEADER_BAND
from rackui import RACK
from rackui import Button
from rackui import CHIP_GAP
from rackui import CHIP_HEIGHT
from rackui import Chip
from rackui import TITLE_SIZE
from rackui import get_chip_width
from rackui import Control
from rackui import Fader
from rackui import IconButton
from rackui import Knob
from rackui import Power
from rackui import Segment
from rackui import Switch
from rackui import draw_faceplate
from rackui import draw_lcd
from rackui import draw_text
from rackui import draw_title
from rackui import fill_rect
from rackui import fit_text
from rackui import get_font
from rackui import get_pen
from rackui import get_db_text
from rackui import get_hz_text
from rackui import get_short_hz
from rackui import set_font


# 판 안쪽 여백은 PAD 하나다. 보이는 내용(글씨·화면 테두리·손잡이 호)이 판 가장자리와
# 이름 띠 아래 금에서 위·아래·왼쪽·오른쪽 모두 이만큼 떨어진다(사용자: 상하좌우 일관).
# EAR + INSET 이 왼쪽 끝 줄이다. 옛 이름을 그대로 두고 합이 PAD 가 되게 맞춘다.
PAD = 14
EAR = 8
INSET = PAD - EAR
U = 40
# 접은 장치의 키. Reason 처럼 이름 띠 한 줄과 켜고 끄기·옮기기만 남는다. 펼친 장치도 맨
# 위 같은 띠를 쓰고 본체는 BODY_TOP 부터, 아래 BOTTOM 을 남긴다.
FOLDED = 30
FOLD = 18
BODY_TOP = HEADER_BAND + 1 + PAD
BOTTOM = PAD
# 믹서와 Analyzer 판은 칸·화면이 촘촘한 판이라 안쪽 여백을 더 작게(사용자).
# 믹서·Analyzer 판 안쪽 여백. 8 도 넓었다(사용자) → 6.
TIGHT_PAD = 6
# Analyzer 의 머리 띠 아래 금에서 화면까지. 금(1 화소)까지 여백으로 읽혀 Analyzer 만 위가 커 보였다(사용자,
# 믹서는 괜찮다) — 금을 넣어 TIGHT_PAD.
TIGHT_TOP = TIGHT_PAD - 1
# 손잡이 한 줄의 보이는 키. 손잡이 칸(64)은 글씨 위아래 여유를 품고 있어 보이는 것은 이만큼.
KNOB_ROW = 62
# 손잡이 칸 맨 위에서 이름 글씨가 보이기 시작하는 곳까지.
KNOB_TOP = 4

TITLES = {
    'preamp': 'Preamp',
    'parametric': 'Parametric EQ',
    'graphic': 'Graphic EQ',
    'delay': 'Delay',
    'stereo': 'Stereo',
    'automaster': 'Auto Master',
    'vst': 'VST plugin',
    'custom': 'Custom lines',
}

ADDABLE = ('preamp', 'parametric', 'graphic', 'delay', 'stereo', 'automaster', 'vst')
# PyWinAudio 의 자체 플러그인. 엔진(audiodg)이 읽을 수 있는 곳에 깔아 둔다(plugin/install.ps1).
AUTOMASTER_PATH = r'C:\Program Files\VSTPlugIns\PyWinAudio\PyWinAudioAutoMaster.dll'
AUTOMASTER_FILE = 'pywinaudioautomaster.dll'
AUTOMASTER_NAME = 'PyWinAudio Auto Master'
# Leveler 시절 이름. 저장된 랙에서 만나면 Auto Master 로 옮긴다(파라미터 이름은 그대로라 값도 이어진다).
OLD_AUTOMASTER_FILE = 'pywinaudioleveler.dll'

BAND_TYPES = (('PK', 'Peak'), ('LSC', 'Low shelf'), ('HSC', 'High shelf'),
              ('HPQ', 'Low cut'), ('LPQ', 'High cut'))
GAIN_TYPES = ('PK', 'LSC', 'HSC')

SCREEN_RANGE = 18.0
GRAPHIC_RANGE = 12.0
MAX_FADERS = 31
MAX_BANDS = 20
# 이 글씨를 보이는 플러그인 파라미터는 손잡이 대신 켜고 끄는 단추로.
SWITCH_WORDS = ('ON', 'OFF', 'ENABLED', 'DISABLED', 'YES', 'NO')


def make_unit(kind):
    if kind == 'preamp':
        return {'kind': kind, 'on': True, 'gain': 0.0}
    if kind == 'parametric':
        return {'kind': kind, 'on': True, 'selected': 0, 'bands': [
            {'type': 'LSC', 'freq': 105.0, 'gain': 0.0, 'q': 0.71, 'on': True},
            {'type': 'PK', 'freq': 1000.0, 'gain': 0.0, 'q': 1.0, 'on': True},
            {'type': 'HSC', 'freq': 8000.0, 'gain': 0.0, 'q': 0.71, 'on': True}]}
    if kind == 'graphic':
        return {'kind': kind, 'on': True, 'freqs': list(eapo.GRAPHIC_FREQUENCIES),
                'gains': [0.0] * len(eapo.GRAPHIC_FREQUENCIES)}
    if kind == 'delay':
        return {'kind': kind, 'on': True, 'ms': 0.0, 'channel': 'all'}
    if kind == 'stereo':
        return {'kind': kind, 'on': True, 'balance': 0.0, 'width': 1.0, 'swap': False}
    if kind == 'vst':
        return {'kind': kind, 'on': True, 'path': '', 'params': [], 'display': [],
                'chunk': None}
    if kind == 'automaster':
        # 엔진에는 보통 VST 줄로 나간다. 랙에서만 기본 장치처럼 보인다.
        return {'kind': 'vst', 'on': True, 'path': AUTOMASTER_PATH, 'params': [], 'display': [],
                'chunk': None, 'name': AUTOMASTER_NAME, 'vendor': 'PyWinAudio'}
    return {'kind': 'custom', 'on': True, 'lines': []}


class Unit:

    # 이름 띠 + 손잡이 한 줄 — 작은 장치의 키.
    height = BODY_TOP + KNOB_ROW + BOTTOM

    def __init__(self, data, rack):
        self.data = data
        self.rack = rack
        self.rect = wx.Rect()
        self.face, self.accent = FACES.get(data['kind'], FACES['custom'])
        self.power = Power(lambda: self.data.get('on', True), self.set_on)
        self.up = IconButton('up', lambda: rack.move(self, -1), tip='Move up')
        self.down = IconButton('down', lambda: rack.move(self, 1), tip='Move down')
        self.remove = IconButton('close', lambda: rack.remove(self), tip='Remove')
        self.fold = IconButton('down', self.toggle_fold, tip='Fold')
        self.extras = []
        self.build()

    def build(self):
        pass

    @property
    def folded(self):
        return bool(self.data.get('folded'))

    def toggle_fold(self):
        '''접는 것은 보기만 바꾼다. 엔진에 가는 글은 그대로라 다시 쓰이지 않는다.'''
        self.data['folded'] = not self.folded
        self.rack.on_unit_change(self)

    def get_controls(self):
        header = [self.fold, self.power, self.up, self.down, self.remove]
        return header if self.folded else header + self.get_body_controls()

    def get_body_controls(self):
        return self.extras

    def set_on(self, value):
        self.data['on'] = bool(value)
        self.changed()

    def changed(self):
        self.rack.on_unit_change(self)

    def get_title(self):
        return self.data.get('title') or TITLES.get(self.data['kind'], 'Unit')

    def get_subtitle(self):
        return ''

    def get_subtitle_tone(self):
        return RACK['dim']

    def get_header_buttons(self):
        '''큰 장치의 위쪽 띠 오른쪽에 놓는 글자 단추.'''
        return []

    def get_height(self, width):
        return FOLDED if self.folded else self.height

    def layout(self, gc, rect):
        '''이름 띠는 접었을 때와 펼쳤을 때가 같은 자리다. 접기·불·제목·부제·옮기기 단추가
        모두 띠 가운데 줄에 선다. 펼치면 그 아래에 본체가 붙을 뿐이다.'''
        self.rect = rect
        # 맨 위 장치는 더 못 올리고, 맨 아래는 더 못 내린다 — 그 단추는 흐리게, 누르지 못하게(사용자).
        units = getattr(self.rack, 'units', [])
        if self in units:
            index = units.index(self)
            self.up.enabled = index > 0
            self.down.enabled = index < len(units) - 1
        left, right = rect.x + EAR + INSET, rect.x + rect.width - EAR - INSET + 2
        middle = rect.y + FOLDED // 2
        self.fold.glyph = 'right' if self.folded else 'down'
        self.fold.tip = 'Unfold' if self.folded else 'Fold'
        self.fold.rect = wx.Rect(left - 4, middle - FOLD // 2, FOLD, FOLD)
        self.power.rect = wx.Rect(left + FOLD, middle - 7, 14, 14)
        x = right
        for button in (self.remove, self.down, self.up):
            x -= IconButton.SIZE
            button.rect = wx.Rect(x, middle - IconButton.SIZE // 2, IconButton.SIZE,
                                  IconButton.SIZE)
            x -= 3
        if not self.folded:
            x -= 8
            for button in reversed(self.get_header_buttons()):
                width = button.get_width(gc)
                x -= width
                button.rect = wx.Rect(x, middle - Button.HEIGHT // 2, width, Button.HEIGHT)
                x -= 6
        self.header_right = x - 8
        if self.folded:
            self.body = wx.Rect(left, rect.y, 0, 0)
            return
        # 띠의 단추들은 제 안에 여백이 있어 2 화소 더 바깥에 선다. 본체는 PAD 그대로.
        body = wx.Rect(left, rect.y + BODY_TOP, rect.x + rect.width - PAD - left,
                       rect.height - BODY_TOP - BOTTOM)
        self.body = body
        self.layout_body(gc, body)

    def layout_body(self, gc, body):
        pass

    def draw(self, gc):
        rect = self.rect
        draw_faceplate(gc, rect.x, rect.y, rect.width, rect.height, self.face, EAR, self.accent)
        left = self.power.rect.x + 22
        draw_title(gc, left, rect.y, self.get_title(), self.get_subtitle(),
                   self.get_subtitle_tone(), max(0, self.header_right - left))
        if self.folded:
            for control in self.get_controls():
                control.draw(gc, self.accent)
            return
        gc.Clip(rect.x, rect.y, rect.width, rect.height)
        self.draw_body(gc)
        for control in self.get_controls():
            control.draw(gc, self.accent)
        gc.ResetClip()

    def draw_body(self, gc):
        pass


def place_knobs(knobs, area, width=58, gc=None):
    '''손잡이를 왼쪽부터 같은 폭으로 늘어놓고 끝 x 를 돌려준다. gc 를 주면 첫 손잡이의
    보이는 왼쪽 끝(호·끝 숫자·이름)이 area 왼쪽에 닿게 칸을 당긴다.'''
    x = area.x
    if gc is not None and knobs:
        x -= max(0, int(width / 2 - knobs[0].get_reach(gc, width)))
    for knob in knobs:
        knob.rect = wx.Rect(x, area.y + (area.height - KNOB_ROW) // 2 - KNOB_TOP, width, KNOB_ROW + KNOB_TOP + 2)
        x += width + 4
    return x


# ---------------------------------------------------------------- Preamp


class PreampUnit(Unit):

    def build(self):
        self.gain = Knob('GAIN', lambda: self.data['gain'], self.put_gain, -30.0, 12.0, 0.0,
                         get_db_text, bipolar=False, step=0.1, ends=('-30', '+12'))
        self.match = Button('Match', self.on_match)
        self.extras = [self.gain, self.match]

    def put_gain(self, value):
        self.data['gain'] = round(value, 1)
        self.changed()

    def get_subtitle(self):
        return 'Level into the rack'

    def get_boost(self):
        return self.rack.get_peak_boost()

    def on_match(self):
        self.put_gain(max(-30.0, min(0.0, -math.ceil(self.get_boost() * 10) / 10)))

    def layout_body(self, gc, body):
        x = place_knobs([self.gain], body, gc=gc)
        width = self.match.get_width(gc)
        left = min(x + 150, body.x + body.width - width)
        self.match.rect = wx.Rect(left, body.y + (body.height - Button.HEIGHT) // 2,
                                  width, Button.HEIGHT)
        self.readout = (x + 6, body.y + body.height / 2)

    def draw_body(self, gc):
        x, middle = self.readout
        boost = self.get_boost()
        draw_text(gc, 'RACK PEAK', x, middle - 15, 7.5, RACK['dim'], engraved=True)
        draw_text(gc, get_db_text(boost), x, middle, 9, RACK['text'])
        tone = RACK['warn'] if boost + self.data['gain'] > 0.05 else RACK['faint']
        hint = 'may clip' if boost + self.data['gain'] > 0.05 else 'headroom ok'
        draw_text(gc, hint, x + 72, middle + 1, 7.5, tone)


# ---------------------------------------------------------------- Parametric EQ


class EqScreen(Control):
    '''응답 곡선 화면. 점을 끌어 주파수와 이득을 함께 옮기고, 빈 곳을 두 번 누르면
    그 자리에 Peak 하나를 더한다.'''

    cursor = wx.CURSOR_ARROW
    HIT = 9

    def __init__(self, unit):
        super().__init__()
        self.unit = unit
        self.dragging = False

    def get_inner(self):
        return wx.Rect(self.rect.x + 26, self.rect.y + 6, self.rect.width - 32,
                       self.rect.height - 20)

    def to_x(self, freq):
        inner = self.get_inner()
        ratio = math.log(freq / dsp.LOW) / math.log(dsp.HIGH / dsp.LOW)
        return inner.x + inner.width * ratio

    def to_y(self, gain):
        inner = self.get_inner()
        gain = min(max(gain, -SCREEN_RANGE), SCREEN_RANGE)
        return inner.y + inner.height * (0.5 - gain / (SCREEN_RANGE * 2))

    def from_point(self, point):
        inner = self.get_inner()
        ratio = min(max((point.x - inner.x) / max(1, inner.width), 0.0), 1.0)
        freq = dsp.LOW * math.exp(math.log(dsp.HIGH / dsp.LOW) * ratio)
        gain = (0.5 - (point.y - inner.y) / max(1, inner.height)) * SCREEN_RANGE * 2
        return freq, min(max(gain, -SCREEN_RANGE), SCREEN_RANGE)

    def get_node(self, band):
        gain = band['gain'] if band['type'] in GAIN_TYPES else 0.0
        return self.to_x(band['freq']), self.to_y(gain)

    def find(self, point):
        best, found = self.HIT ** 2, -1
        for index, band in enumerate(self.unit.data['bands']):
            x, y = self.get_node(band)
            distance = (x - point.x) ** 2 + (y - point.y) ** 2
            if distance <= best:
                best, found = distance, index
        return found

    def on_down(self, point, shift):
        super().on_down(point, shift)
        index = self.find(point)
        self.dragging = index >= 0
        if self.dragging:
            self.unit.select(index)

    def on_drag(self, point, shift):
        if not self.dragging:
            return
        band = self.unit.get_band()
        if band is None:
            return
        freq, gain = self.from_point(point)
        band['freq'] = round(freq, 1)
        if band['type'] in GAIN_TYPES:
            band['gain'] = round(gain, 1)
        self.unit.changed()

    def on_up(self, point):
        self.pressed = False
        self.dragging = False

    def on_dclick(self, point):
        if self.find(point) >= 0:
            return
        freq, gain = self.from_point(point)
        self.unit.add_band({'type': 'PK', 'freq': round(freq, 1), 'gain': round(gain, 1),
                            'q': 1.0, 'on': True})

    def draw(self, gc, accent):
        rect = self.rect
        draw_lcd(gc, rect)
        inner = self.get_inner()

        gc.SetPen(get_pen(gc, RACK['lcd_grid'], 1))
        for freq in (50, 100, 200, 500, 1000, 2000, 5000, 10000):
            x = round(self.to_x(freq)) + 0.5
            gc.StrokeLine(x, inner.y, x, inner.y + inner.height)
            if freq in (100, 1000, 10000):
                draw_text(gc, get_short_hz(freq), x, inner.y + inner.height + 1, 7,
                          RACK['lcd_text'], align='center')
        for gain in (-12, -6, 6, 12):
            y = round(self.to_y(gain)) + 0.5
            gc.StrokeLine(inner.x, y, inner.x + inner.width, y)
            draw_text(gc, '%+d' % gain, inner.x - 4, y - 6, 7, RACK['lcd_text'],
                      align='right')
        gc.SetPen(get_pen(gc, RACK['lcd_axis'], 1))
        y = round(self.to_y(0)) + 0.5
        gc.StrokeLine(inner.x, y, inner.x + inner.width, y)
        draw_text(gc, '0', inner.x - 4, y - 6, 7, RACK['lcd_text'], align='right')

        gc.Clip(inner.x, inner.y, inner.width, inner.height)
        count = max(64, inner.width // 2)
        freqs = dsp.get_frequencies(count)
        bands = self.unit.data['bands']
        on = self.unit.data.get('on', True)
        band = self.unit.get_band()
        if band is not None and band.get('on', True):
            self.draw_fill(gc, freqs, dsp.get_band_curve(band, freqs), accent)
        total = dsp.get_parametric_curve(bands, freqs)
        self.draw_curve(gc, freqs, total, accent if on else RACK['faint'], 2)
        gc.ResetClip()

        selected = self.unit.data.get('selected', 0)
        for index, item in enumerate(bands):
            x, y = self.get_node(item)
            lit = index == selected
            radius = 7 if lit else 5.5
            colour = accent if item.get('on', True) else RACK['faint']
            gc.SetPen(get_pen(gc, '#ffffff' if lit else colour, 1.5))
            gc.SetBrush(wx.Brush(wx.Colour(colour if lit else RACK['lcd'])))
            gc.DrawEllipse(x - radius, y - radius, radius * 2, radius * 2)
            draw_text(gc, str(index + 1), x, y - 6, 7, RACK['lcd'] if lit else colour,
                      bold=True, align='center')

    def get_points(self, freqs, curve):
        return [(self.to_x(freq), self.to_y(value)) for freq, value in zip(freqs, curve)]

    def draw_curve(self, gc, freqs, curve, colour, width):
        points = self.get_points(freqs, curve)
        path = gc.CreatePath()
        path.MoveToPoint(*points[0])
        for point in points[1:]:
            path.AddLineToPoint(*point)
        gc.SetPen(gc.CreatePen(wx.GraphicsPenInfo(wx.Colour(colour)).Width(width)
                               .Join(wx.JOIN_ROUND)))
        gc.SetBrush(wx.TRANSPARENT_BRUSH)
        gc.StrokePath(path)

    def draw_fill(self, gc, freqs, curve, colour):
        points = self.get_points(freqs, curve)
        zero = self.to_y(0)
        path = gc.CreatePath()
        path.MoveToPoint(points[0][0], zero)
        for point in points:
            path.AddLineToPoint(*point)
        path.AddLineToPoint(points[-1][0], zero)
        path.CloseSubpath()
        base = wx.Colour(colour)
        gc.SetPen(wx.TRANSPARENT_PEN)
        gc.SetBrush(wx.Brush(wx.Colour(base.Red(), base.Green(), base.Blue(), 46)))
        gc.FillPath(path)


class ParametricUnit(Unit):

    height = BODY_TOP + 164 + BOTTOM
    PANEL = 236
    # 이보다 좁으면 화면을 위에, 밴드 조작부를 그 아래에 둔다.
    SIDE_BY_SIDE = 600
    SCREEN_HEIGHT = 136
    # 손잡이 이름과 호 사이를 넓힌 만큼(3) 더 — 실측 아래 여백 14.
    PANEL_HEIGHT = 138

    def build(self):
        self.screen = EqScreen(self)
        self.previous = IconButton('left', lambda: self.step(-1), tip='Previous band')
        self.next = IconButton('right', lambda: self.step(1), tip='Next band')
        self.add = Button('Add', self.on_add)
        self.drop = Button('Delete', self.on_drop)
        self.band_power = Power(self.get_band_on, self.put_band_on)
        self.kind = Segment(BAND_TYPES, lambda: self.get_value('type'),
                            lambda value: self.put_value('type', value), vertical=True)
        self.freq = Knob('FREQ', lambda: self.get_value('freq', 1000.0),
                         lambda value: self.put_value('freq', round(value, 1)),
                         20.0, 20000.0, 1000.0, get_hz_text, log=True, ends=('20', '20k'))
        self.gain = Knob('GAIN', lambda: self.get_value('gain', 0.0),
                         lambda value: self.put_value('gain', round(value, 1)),
                         -SCREEN_RANGE, SCREEN_RANGE, 0.0, get_db_text, bipolar=True,
                         ends=('-18', '+18'))
        self.q = Knob('Q', lambda: self.get_value('q', 1.0),
                      lambda value: self.put_value('q', round(value, 2)),
                      0.1, 10.0, 0.71, lambda value: '%.2f' % value, log=True,
                      ends=('.1', '10'))
        self.extras = [self.screen, self.previous, self.next, self.add, self.drop,
                       self.band_power, self.kind, self.freq, self.gain, self.q]

    def get_subtitle(self):
        count = len(self.data['bands'])
        return '%d band%s' % (count, '' if count == 1 else 's')

    def get_band(self):
        bands = self.data['bands']
        if not bands:
            return None
        index = min(max(self.data.get('selected', 0), 0), len(bands) - 1)
        self.data['selected'] = index
        return bands[index]

    def get_value(self, key, fallback=None):
        band = self.get_band()
        return band.get(key, fallback) if band else fallback

    def put_value(self, key, value):
        band = self.get_band()
        if band is None:
            return
        band[key] = value
        if key == 'type' and value in ('HPQ', 'LPQ'):
            band['gain'] = 0.0
        self.changed()

    def get_band_on(self):
        band = self.get_band()
        return bool(band and band.get('on', True))

    def put_band_on(self, value):
        self.put_value('on', bool(value))

    def select(self, index):
        self.data['selected'] = index
        self.rack.Refresh()

    def step(self, delta):
        count = len(self.data['bands'])
        if count:
            self.select((self.data.get('selected', 0) + delta) % count)

    def add_band(self, band):
        if len(self.data['bands']) >= MAX_BANDS:
            return
        self.data['bands'].append(band)
        self.data['selected'] = len(self.data['bands']) - 1
        self.changed()

    def on_add(self):
        band = self.get_band()
        freq = min(band['freq'] * 2, 16000.0) if band else 1000.0
        self.add_band({'type': 'PK', 'freq': freq, 'gain': 0.0, 'q': 1.0, 'on': True})

    def on_drop(self):
        bands = self.data['bands']
        if not bands:
            return
        bands.pop(self.data.get('selected', 0))
        self.data['selected'] = max(0, min(self.data.get('selected', 0), len(bands) - 1))
        self.changed()

    def get_height(self, width):
        if self.folded:
            return FOLDED
        if width < self.SIDE_BY_SIDE:
            return BODY_TOP + self.SCREEN_HEIGHT + 10 + self.PANEL_HEIGHT + BOTTOM
        return self.height

    def layout_body(self, gc, body):
        if self.rect.width < self.SIDE_BY_SIDE:
            panel = min(self.PANEL + 40, body.width)
            self.screen.rect = wx.Rect(body.x + 1, body.y + 1, body.width - 2, self.SCREEN_HEIGHT)
            x = body.x
            top = body.y + self.SCREEN_HEIGHT + 12
        else:
            panel = min(self.PANEL, body.width // 2)
            # 화면 테두리(1 화소 바깥)가 본체 끝에 닿게.
            self.screen.rect = wx.Rect(body.x + 1, body.y + 1, body.width - panel - 16,
                                       body.height - 2)
            x = body.x + body.width - panel
            top = body.y
        self.band_power.rect = wx.Rect(x, top + 4, 14, 14)
        self.previous.rect = wx.Rect(x + 22, top + 2, IconButton.SIZE, IconButton.SIZE)
        self.band_label = (x + 22 + IconButton.SIZE + 34, top + 4)
        self.next.rect = wx.Rect(x + 22 + IconButton.SIZE + 68, top + 2, IconButton.SIZE,
                                 IconButton.SIZE)
        right = x + panel - 1
        width = self.drop.get_width(gc)
        self.drop.rect = wx.Rect(right - width, top, width, Button.HEIGHT)
        add = self.add.get_width(gc)
        self.add.rect = wx.Rect(right - width - 4 - add, top, add, Button.HEIGHT)

        lower = top + Button.HEIGHT + 10
        self.kind.rect = wx.Rect(x, lower, 76, 5 * 21)
        knobs = wx.Rect(x + 84, lower + 14, panel - 84, 64)
        place_knobs([self.freq, self.gain, self.q], knobs, width=(panel - 84 - 8) // 3)

        enabled = bool(self.data['bands'])
        for control in (self.previous, self.next, self.drop, self.band_power, self.kind,
                        self.freq, self.q):
            control.enabled = enabled
        self.add.enabled = len(self.data['bands']) < MAX_BANDS
        self.gain.enabled = enabled and self.get_value('type') in GAIN_TYPES

    def draw_body(self, gc):
        x, y = self.band_label
        count = len(self.data['bands'])
        text = 'BAND %d / %d' % (self.data.get('selected', 0) + 1, count) if count else 'NO BANDS'
        draw_text(gc, text, x, y, 8, RACK['text'], bold=True, align='center', engraved=True)


# ---------------------------------------------------------------- Graphic EQ


class GraphicUnit(Unit):

    height = BODY_TOP + 124 + BOTTOM

    def build(self):
        self.flat = Button('Flat', self.on_flat)
        self.resample = Button('Make 15 bands', self.on_resample)
        self.faders = []
        if len(self.data['freqs']) <= MAX_FADERS:
            for index, freq in enumerate(self.data['freqs']):
                self.faders.append(Fader(
                    get_short_hz(freq),
                    lambda index=index: self.data['gains'][index],
                    lambda value, index=index: self.put_gain(index, value),
                    -GRAPHIC_RANGE, GRAPHIC_RANGE, 0.0, get_db_text))
        self.extras = [self.flat] + self.faders + ([] if self.faders else [self.resample])

    def get_header_buttons(self):
        return [self.flat]

    def get_subtitle(self):
        count = len(self.data['freqs'])
        if self.faders:
            return '%d bands' % count
        return '%d points, imported' % count

    def put_gain(self, index, value):
        self.data['gains'][index] = round(value, 1)
        self.changed()

    def on_flat(self):
        self.data['gains'] = [0.0] * len(self.data['gains'])
        self.changed()

    def on_resample(self):
        freqs = list(eapo.GRAPHIC_FREQUENCIES)
        curve = dsp.get_graphic_curve(self.data['freqs'], self.data['gains'], freqs)
        self.data['freqs'] = freqs
        self.data['gains'] = [round(min(max(value, -GRAPHIC_RANGE), GRAPHIC_RANGE), 1)
                              for value in curve]
        self.build()
        self.changed()

    def layout_body(self, gc, body):
        if not self.faders:
            self.screen = wx.Rect(body.x, body.y + 2, body.width - 140, body.height - 4)
            width = self.resample.get_width(gc)
            self.resample.rect = wx.Rect(body.x + body.width - width,
                                         body.y + (body.height - Button.HEIGHT) // 2,
                                         width, Button.HEIGHT)
            return
        # 막대 칸 위 14 는 끌 때 값이 뜨는 자리라 평소엔 비어 있다. 그만큼 위로 올려 눈금
        # 맨 위 글씨가 본체 끝에 닿게, 아래 주파수 글씨도 끝에 닿게 늘인다.
        self.scale = wx.Rect(body.x, body.y, 26, body.height)
        area = wx.Rect(body.x + 30, body.y - 11, body.width - 30, body.height + 13)
        width = area.width / len(self.faders)
        # 칸이 좁으면 주파수 이름을 건너뛰며 단다. 서로 겹쳐 아무것도 못 읽게 되느니.
        skip = max(1, math.ceil(26 / max(1, width)))
        for index, fader in enumerate(self.faders):
            fader.rect = wx.Rect(round(area.x + width * index), area.y, round(width),
                                 area.height)
            fader.show_label = index % skip == 0

    def draw_body(self, gc):
        if not self.faders:
            draw_lcd(gc, self.screen)
            inner = wx.Rect(self.screen.x + 6, self.screen.y + 6, self.screen.width - 12,
                            self.screen.height - 12)
            freqs = dsp.get_frequencies(max(64, inner.width // 2))
            curve = dsp.get_graphic_curve(self.data['freqs'], self.data['gains'], freqs)
            low = min(curve + [-6.0])
            high = max(curve + [6.0])
            path = gc.CreatePath()
            for index, value in enumerate(curve):
                x = inner.x + inner.width * index / (len(curve) - 1)
                y = inner.y + inner.height * (high - value) / (high - low)
                if index:
                    path.AddLineToPoint(x, y)
                else:
                    path.MoveToPoint(x, y)
            gc.SetPen(get_pen(gc, self.accent, 2))
            gc.StrokePath(path)
            return
        fader = self.faders[0]
        top, bottom = fader.get_slot()
        for gain in (-12, -6, 0, 6, 12):
            y = fader.to_y(gain)
            fill_rect(gc, '#000000' if gain else RACK['faint'], self.scale.x + 20, y,
                      self.body.width - 20, 1)
            draw_text(gc, '%+d' % gain if gain else '0', self.scale.x + 17, y - 6, 7,
                      RACK['dim'], align='right', engraved=True)


# ---------------------------------------------------------------- Delay · Stereo


class DelayUnit(Unit):

    def build(self):
        self.time = Knob('TIME', lambda: self.data['ms'], self.put_time, 0.0, 300.0, 0.0,
                         lambda value: '%.1f ms' % value, step=0.1, ends=('0', '300'))
        self.channel = Segment((('all', 'Both'), ('L', 'Left'), ('R', 'Right')),
                               lambda: self.data.get('channel', 'all'), self.put_channel)
        self.extras = [self.time, self.channel]

    def get_subtitle(self):
        channel = self.data.get('channel', 'all')
        return 'Both channels' if channel == 'all' else '%s channel only' % (
            'Left' if channel == 'L' else 'Right')

    def put_time(self, value):
        self.data['ms'] = round(value, 1)
        self.changed()

    def put_channel(self, value):
        self.data['channel'] = value
        self.changed()

    def layout_body(self, gc, body):
        x = place_knobs([self.time], body, gc=gc)
        width = max(90, min(168, body.x + body.width - x - 12))
        self.channel.rect = wx.Rect(x + 12, body.y + (body.height - 24) // 2, width, 24)


def get_balance_text(value):
    if abs(value) < 0.005:
        return 'Center'
    return '%s %d%%' % ('R' if value > 0 else 'L', round(abs(value) * 100))


def get_width_text(value):
    return 'Mono' if value < 0.005 else '%d%%' % round(value * 100)


class StereoUnit(Unit):

    def build(self):
        self.balance = Knob('BALANCE', lambda: self.data['balance'],
                            lambda value: self.put('balance', round(value, 2)),
                            -1.0, 1.0, 0.0, get_balance_text, bipolar=True, ends=('L', 'R'))
        self.width = Knob('WIDTH', lambda: self.data['width'],
                          lambda value: self.put('width', round(value, 2)),
                          0.0, 2.0, 1.0, get_width_text, bipolar=True, ends=('0', '200'))
        self.swap = Button('Swap L/R', lambda: self.put('swap', not self.data.get('swap')),
                           active=lambda: bool(self.data.get('swap')))
        self.extras = [self.balance, self.width, self.swap]

    def get_subtitle(self):
        return 'Balance, width, swap'

    def put(self, key, value):
        self.data[key] = value
        self.changed()

    def layout_body(self, gc, body):
        x = place_knobs([self.balance, self.width], body, gc=gc)
        width = self.swap.get_width(gc)
        self.swap.rect = wx.Rect(x + 12, body.y + (body.height - Button.HEIGHT) // 2,
                                 width, Button.HEIGHT)


# ---------------------------------------------------------------- VST


class VstUnit(Unit):
    '''플러그인은 손을 댈 때에야 이 프로세스에 올린다. 그 전에는 저장해 둔 이름과
    값으로 그린다 — 앱을 켤 때마다 남의 DLL 을 모두 올릴 까닭이 없다.'''

    # 손잡이 칸. 'WIDE AMOUNT' 같은 이름이 잘리지 않을 만큼. 칸이 모자라면 줄을 바꿔 판이
    # 아래로 길어진다(사용자: 좁은 화면에서 줄바꿈).
    KNOB = 68
    KNOB_GAP = 4
    # 줄 사이: 12 + 가로 금 1 + 12 (사용자: 여백 좀 더).
    RULE_GAP = 12
    ROW_GAP = RULE_GAP * 2 + 1
    # Edit·Choose 단추 기둥의 폭. 키를 셀 때(gc 없음)와 놓을 때가 같은 값을 써야 줄 수가 맞는다.
    BUTTONS = 76
    # 플러그인이 알려 준 구역 사이의 틈. 가운데에 세로 금 하나.
    SEPARATOR = 21
    # PyWinAudio Auto Master 의 보정 계기 줄(이름·값 한 줄 + 막대).
    METER_ROW = 26
    METER_CELL = 112
    METER_GAP = 16
    # 모노 채움은 대역마다(150–600 Hz·600 Hz–3 kHz·3 kHz 위 — 사용자), 위상은 맞춘 시간(± ms)과 극성.
    METERS = (('agc', 'AGC', -12.0, 18.0, True), ('balance', 'BALANCE', -6.0, 6.0, True),
              ('side', 'WIDTH CUT', -6.0, 0.0, False), ('phase', 'PHASE', -2.0, 2.0, True),
              ('fill_low', 'FILL LOW', -30.0, 0.0, False), ('fill_mid', 'FILL MID', -30.0, 0.0, False),
              ('fill_high', 'FILL HIGH', -30.0, 0.0, False), ('limiter', 'LIMITER', -12.0, 0.0, False))
    LIMITER_FALL = 12.0
    meter_values = None
    meter_rect = None

    plugin = None
    editor = None
    notice = ''
    notice_timer = None
    NOTICE_TIME = 4000

    def show_notice(self, text):
        self.notice = text
        if self.notice_timer is not None and self.notice_timer.IsRunning():
            self.notice_timer.Stop()
        self.notice_timer = wx.CallLater(self.NOTICE_TIME, self.clear_notice)

    def clear_notice(self):
        self.notice = ''
        if self.rack:
            self.rack.Refresh()

    def build(self):
        '''이름이 바뀌면 손잡이를 다시 만든다. 올려 둔 플러그인과 편집기는 그대로 둔다.'''
        # 예전에는 이 알림을 잘못으로 저장해 두어 사라지지 않았다. 남아 있으면 걷는다.
        if self.data.get('error') == 'This plugin has no editor of its own':
            self.data.pop('error')
            self.data['has_editor'] = False
        self.edit = Button('Edit', self.on_edit)
        self.choose = Button('Choose…', self.on_choose)
        self.knobs = []
        for index, item in enumerate(self.data.get('params', ())):
            if self.is_switch(index):
                self.knobs.append(Switch(
                    self.get_short_name(item[0]),
                    lambda index=index: self.data['params'][index][1],
                    lambda value, index=index: self.put_param(index, value),
                    lambda value, index=index: self.get_display(index, value)))
                continue
            self.knobs.append(Knob(
                self.get_short_name(item[0]),
                lambda index=index: self.data['params'][index][1],
                lambda value, index=index: self.put_param(index, value),
                0.0, 1.0, lambda index=index: self.get_default(index),
                lambda value, index=index: self.get_display(index, value)))
        self.visible = []
        self.extras = [self.edit, self.choose]

    def get_body_controls(self):
        return self.extras + (self.visible if self.shows_controls() else [])

    def shows_meters(self):
        return self.is_automaster() and self.data.get('show_meters', True)

    def shows_controls(self):
        return not self.is_automaster() or self.data.get('show_controls', True)

    def is_switch(self, index):
        '''VST2 의 파라미터는 모두 0~1 실수라 켜고 끄는 값을 따로 알려 주지 않는다. 플러그인이
        보여 주는 글씨가 ON·OFF 류면 켜고 끄는 단추로 본다.'''
        # 플러그인이 직접 알려 주면(VstParameterProperties 의 IsSwitch) 그것을 믿는다.
        switches = self.data.get('switches') or []
        if index < len(switches) and switches[index] is not None:
            return bool(switches[index])
        display = self.data.get('display') or []
        text = display[index].strip().upper() if index < len(display) else ''
        return text in SWITCH_WORDS

    def get_short_name(self, name):
        return name.upper()

    def get_default(self, index):
        '''플러그인이 갓 올라왔을 때의 값. 저장한 값을 되돌리기 전에 읽어 둔다 — 지금 값을 쓰면
        두 번 눌러도 마지막에 쓴 값으로 돌아갔다(사용자).'''
        # 저장해 둔 defaults 는 옛 빌드의 것일 수 있다. 플러그인을 올려 지금 빌드에게 묻는다.
        self.ensure_plugin()
        defaults = self.data.get('defaults') or []
        if index < len(defaults):
            return defaults[index]
        return self.data['params'][index][1]

    def get_title(self):
        return self.data.get('name') or 'VST plugin'

    def get_subtitle(self):
        if self.data.get('error'):
            return self.data['error']
        if self.notice:
            return self.notice
        if not self.data.get('path'):
            return 'Choose a plugin file'
        if not os.path.exists(self.data['path']):
            return 'Plugin file not found'
        return self.data.get('vendor') or os.path.basename(self.data['path'])

    def get_subtitle_tone(self):
        path = self.data.get('path')
        if self.data.get('error') or self.notice or (path and not os.path.exists(path)):
            return RACK['warn']
        return RACK['dim']

    def get_display(self, index, value):
        if self.plugin is not None:
            return '%s %s' % (self.plugin.get_display(index), self.plugin.get_label(index))
        display = self.data.get('display') or []
        if index < len(display) and display[index]:
            return display[index]
        return '%d%%' % round(value * 100)

    def ensure_plugin(self):
        if self.plugin is not None:
            return self.plugin
        path = self.data.get('path')
        if not path or not os.path.exists(path):
            return None
        import vsthost
        try:
            plugin = vsthost.Plugin(path)
        except Exception as error:
            self.data['error'] = str(error) or 'Could not load the plugin'
            self.rack.Refresh()
            return None
        self.data.pop('error', None)
        self.plugin = plugin
        self.data['defaults'] = [round(plugin.get_value(index), 6) for index in range(plugin.count)]
        self.apply_state()
        self.read_state()
        return plugin

    def apply_state(self):
        '''저장해 둔 값을 플러그인에 되돌린다. 덩어리가 있으면 그것이 전부다.'''
        plugin = self.plugin
        if self.data.get('chunk') and plugin.uses_chunks:
            plugin.set_chunk(self.data['chunk'])
            return
        names = {plugin.get_name(index): index for index in range(plugin.count)}
        for name, value in self.data.get('params', ()):
            if name in names:
                plugin.set_value(names[name], value)

    def read_state(self):
        plugin = self.plugin
        if plugin is None:
            return False
        params = [[plugin.get_name(index), round(plugin.get_value(index), 6)]
                  for index in range(plugin.count)]
        display = ['%s %s' % (plugin.get_display(index), plugin.get_label(index))
                   for index in range(plugin.count)]
        properties = [plugin.get_properties(index) for index in range(plugin.count)]
        self.data['has_editor'] = plugin.has_editor
        self.data['groups'] = [category for category, switch in properties]
        self.data['switches'] = [switch for category, switch in properties]
        chunk = plugin.get_chunk() if plugin.uses_chunks else None
        changed = (params != self.data.get('params') or chunk != self.data.get('chunk'))
        names_changed = [p[0] for p in params] != [p[0] for p in self.data.get('params', ())]
        self.data['params'] = params
        self.data['display'] = [text.strip() for text in display]
        self.data['chunk'] = chunk
        self.data['name'] = plugin.name
        self.data['vendor'] = plugin.vendor
        if names_changed:
            self.build()
        return changed

    def put_param(self, index, value):
        plugin = self.ensure_plugin()
        self.data['params'][index][1] = round(value, 6)
        if plugin is not None and index < plugin.count:
            plugin.set_value(index, value)
            # 플러그인이 값을 거절하거나(LoudMax 는 Fader Link 가 켜지면 Output 이 끝에 닿은 채로
            # Thresh 를 올리지 못한다) 다른 값을 함께 움직인다. 넣은 값을 믿지 말고 모두 다시
            # 읽어 손잡이·숫자를 플러그인에 맞춘다.
            self.read_state()
            # 거절당하면 손잡이가 말없이 서 있어 고장처럼 보였다(사용자). 잠깐 까닭을 띄운다.
            if abs(self.data['params'][index][1] - value) > 0.01:
                self.show_notice('%s: held by the plugin (another setting limits it)' %
                                 self.get_short_name(self.data['params'][index][0]))
        self.changed()

    def on_edit(self):
        if self.editor:
            self.editor.Raise()
            return
        plugin = self.ensure_plugin()
        if plugin is None:
            return
        if not plugin.has_editor:
            # 잘못이 아니라 알림이다. 잠깐 띄우고 사라진다(사용자). Edit 도 그 뒤로는 흐리게.
            self.data['has_editor'] = False
            self.show_notice('This plugin has no editor of its own')
            self.rack.Refresh()
            return
        from vsteditor import EditorFrame
        self.editor = EditorFrame(self.rack.GetTopLevelParent(), self)

    def on_editor_closed(self):
        self.editor = None
        if self.read_state():
            self.changed()
        else:
            self.rack.Refresh()

    def on_editor_poll(self):
        if self.read_state():
            self.changed()

    def pick_path(self):
        '''고른 플러그인 파일 경로. 그만두면 None.'''
        start = os.path.dirname(self.data.get('path') or '') or self.rack.get_plugin_folder()
        with wx.FileDialog(self.rack, 'Choose a VST2 plugin', defaultDir=start,
                           wildcard='VST2 plugin (*.dll)|*.dll',
                           style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as dialog:
            if dialog.ShowModal() != wx.ID_OK:
                return None
            return dialog.GetPath()

    def on_choose(self):
        path = self.pick_path()
        if path is None:
            return False
        self.load(path)
        return True

    def load(self, path):
        self.close()
        self.data.update({'path': path, 'params': [], 'display': [], 'chunk': None,
                          'name': os.path.splitext(os.path.basename(path))[0], 'vendor': ''})
        self.data.pop('error', None)
        if self.ensure_plugin() is None:
            self.data['path'] = ''
            self.build()
            self.rack.Refresh()
            return
        self.build()
        self.changed()

    def close(self):
        # 편집기 창보다 플러그인 쪽 편집기를 먼저 닫는다. 담긴 창이 사라진 뒤에
        # 닫으라고 하면 플러그인이 없는 창을 만지다 죽는다.
        if self.editor:
            self.editor.timer.Stop()
            if self.plugin is not None:
                self.plugin.close_editor()
            self.editor.Destroy()
            self.editor = None
        if self.plugin is not None:
            self.plugin.close()
            self.plugin = None

    def draw_meters(self, gc):
        '''단계마다 지금 얼마나 고치고 있는지: 이름, 값, 막대. 양쪽으로 가는 값(AGC·좌우)은
        0 에서 양쪽으로, 줄이기만 하는 값은 오른쪽 끝(0)에서 왼쪽으로 자란다.'''
        rect = self.meter_rect
        values = self.meter_values
        gap = self.METER_GAP
        columns = self.get_meter_columns(rect.width)
        width = (rect.width - gap * (columns - 1)) / columns
        for index, (key, label, low, high, bipolar) in enumerate(self.METERS):
            row, column = divmod(index, columns)
            x = rect.x + column * (width + gap)
            top = rect.y + row * (self.METER_ROW + self.RULE_GAP)
            draw_text(gc, label, x, top, 7, RACK['dim'], bold=True)
            value = None if values is None else values.get('limiter_hold' if key == 'limiter' else key)
            fill = key.startswith('fill')
            if value is None:
                text = '--'
            elif fill and value <= low:
                text = 'off'
            elif key == 'phase':
                delay = '' if abs(value) < 0.05 else '%+.1f ms' % value
                text = ('INV ' + delay).strip() if values.get('phase_flip') else (delay or 'OK')
            else:
                shown = 0.0 if abs(value) < 0.05 else value  # '-0.0' 이 뜨지 않게
                text = '%+.1f dB' % shown if bipolar else '%.1f dB' % min(0.0, shown)
            draw_text(gc, text, x + width, top, 7, RACK['text'] if value is not None else
                      RACK['faint'], align='right')
            bar = wx.Rect(int(x), top + 17, int(width), 5)
            fill_rect(gc, RACK['track'], bar.x, bar.y, bar.width, bar.height, 2)
            zero = bar.x + bar.width * (0.0 - low) / (high - low)
            if value is not None and not (fill and value <= low):
                v = min(max(value, low), high)
                at = bar.x + bar.width * (v - low) / (high - low)
                if fill:
                    left, right = bar.x, at
                else:
                    left, right = min(at, zero), max(at, zero)
                if right - left >= 1:
                    fill_rect(gc, self.accent, left, bar.y, right - left, bar.height, 2)
                    # 가운데 0 에서 자라는 막대는 0 쪽이 시작점이라 각지게 — 둥글면 끝처럼 보인다(사용자).
                    if bipolar and right - left > 2:
                        side = left if at >= zero else right - 2
                        fill_rect(gc, self.accent, side, bar.y, 2, bar.height)
            if bipolar:
                fill_rect(gc, RACK['dim'], zero, bar.y - 2, 1, bar.height + 4)

    # 랙 손잡이로 둘 까닭이 없는 것 — 편집기 창 크기만 바꾸는 단추(사용자).
    HIDDEN = ('large gui',)

    def is_hidden(self, index):
        params = self.data.get('params') or []
        return index < len(params) and params[index][0].strip().lower() in self.HIDDEN

    def get_groups(self):
        '''이어진 같은 구역 번호끼리 묶은 손잡이 차례들. 구역을 모르면 한 묶음.'''
        groups_of = self.data.get('groups') or []
        groups = []
        for index in range(len(self.knobs)):
            if self.is_hidden(index):
                continue
            category = groups_of[index] if index < len(groups_of) else 0
            if groups and groups[-1][0] == category:
                groups[-1][1].append(index)
            else:
                groups.append((category, [index]))
        return [indices for category, indices in groups]

    def flow(self, body_width):
        '''손잡이 자리(줄, x)와 구역 금 자리(줄, x), 줄 수. 한 구역은 되도록 한 줄에 함께 두고,
        남은 자리에 안 들어가면 다음 줄로 넘긴다. 한 줄보다 긴 구역은 그 안에서 줄을 바꾼다.'''
        # 첫 줄만 오른쪽 Edit·Choose 단추 기둥을 비운다. 둘째 줄부터는 단추 아래까지 다 쓴다(사용자).
        def get_room(row):
            return max(self.KNOB, body_width - (self.BUTTONS + 12 if row == 0 and self.BUTTONS else 0))
        places, separators = {}, []
        row = x = 0
        for group in self.get_groups():
            width = len(group) * self.KNOB + (len(group) - 1) * self.KNOB_GAP
            room = get_room(row)
            if x > 0:
                if x + self.SEPARATOR + width <= room:
                    separators.append((row, x + self.SEPARATOR // 2))
                    x += self.SEPARATOR
                else:
                    row, x = row + 1, 0
            for index in group:
                if x > 0 and x + self.KNOB > get_room(row):
                    row, x = row + 1, 0
                places[index] = (row, x)
                x += self.KNOB + self.KNOB_GAP
            x -= self.KNOB_GAP
        return places, separators, row + 1

    def is_automaster(self):
        return self.data.get('name') == AUTOMASTER_NAME

    def get_height(self, width):
        if self.folded:
            return FOLDED
        parts = []
        if self.shows_meters():
            rows = self.get_meter_rows(width - PAD * 2)
            parts.append(rows * self.METER_ROW + (rows - 1) * self.RULE_GAP)
        if self.shows_controls():
            rows = self.flow(width - PAD * 2)[2]
            parts.append(rows * KNOB_ROW + (rows - 1) * self.ROW_GAP)
        return BODY_TOP + sum(parts) + self.ROW_GAP * (len(parts) - 1) + BOTTOM

    def get_meter_columns(self, body_width):
        '''계기 칸이 이름·값이 겹치지 않을 만큼 넓게 — 좁으면 줄을 바꾼다(사용자).'''
        return max(1, min(len(self.METERS), (body_width + self.METER_GAP) //
                          (self.METER_CELL + self.METER_GAP)))

    def get_meter_rows(self, body_width):
        return math.ceil(len(self.METERS) / self.get_meter_columns(body_width))

    def update_meters(self, elapsed):
        '''플러그인이 audiodg 안에서 적은 값을 읽는다. 리미터는 블록마다 들쭉날쭉해 봉우리를
        잡고 천천히 놓는다. 값이 바뀌었으면 참.'''
        from automastermeter import READER
        values = READER.read()
        old = self.meter_values
        if values is not None:
            held = (old or {}).get('limiter_hold', 0.0) + self.LIMITER_FALL * elapsed
            values['limiter_hold'] = min(0.0, min(values['limiter'], held))
        self.meter_values = values
        return values != old

    def layout_body(self, gc, body):
        width = max(1, self.BUTTONS)
        # 단추 테두리는 칸 1 화소 바깥까지 보인다. 실측 오른쪽 여백을 PAD 에 맞춘다.
        right = body.x + body.width - 1
        middle = body.y + (KNOB_ROW - Button.HEIGHT * 2 - 6) // 2
        self.edit.rect = wx.Rect(right - width, middle, width, Button.HEIGHT)
        self.choose.rect = wx.Rect(right - width, middle + Button.HEIGHT + 6, width,
                                   Button.HEIGHT)
        path = self.data.get('path')
        self.edit.enabled = bool(path and os.path.exists(path) and
                                 self.data.get('has_editor', True))
        places, separators, rows = self.flow(body.width)
        self.visible = [knob for index, knob in enumerate(self.knobs) if index in places]
        # 줄 맨 앞 손잡이들 가운데 가장 넓게 퍼지는 것에 맞춰 모든 줄을 같은 만큼 당긴다 —
        # 줄마다 따로 당기면 기둥이 어긋난다.
        first = [self.knobs[index] for index, (row, x) in places.items() if x == 0]
        shift = 0
        if first:
            shift = max(0, int(self.KNOB / 2 - max(knob.get_reach(gc, self.KNOB)
                                                    for knob in first)))
        # Auto Master 는 보정 계기를 맨 위에, 그 아래 금 하나, 그 아래 손잡이들(사용자).
        top = body.y
        self.meter_rect = None
        meter_separator = []
        if self.shows_meters():
            meter_rows = self.get_meter_rows(body.width)
            height = meter_rows * self.METER_ROW + (meter_rows - 1) * self.RULE_GAP
            self.meter_rect = wx.Rect(body.x, body.y, body.width, height)
            top = body.y + height + self.ROW_GAP
            meter_separator = [wx.Rect(body.x, top - self.RULE_GAP - 1, body.width, 1)]
        if not self.shows_controls():
            # 상세 설정을 숨기면 계기 줄만 남는다(사용자). 손잡이는 자리도 받지 않는다.
            for knob in self.knobs:
                knob.rect = wx.Rect()
            self.separators = []
            return
        for index, knob in enumerate(self.knobs):
            if index not in places:
                knob.rect = wx.Rect()
                continue
            row, x = places[index]
            y = top + row * (KNOB_ROW + self.ROW_GAP) - KNOB_TOP
            knob.rect = wx.Rect(body.x - shift + x, y, self.KNOB, KNOB_ROW + KNOB_TOP + 2)
        self.separators = [wx.Rect(body.x - shift + x, top + row * (KNOB_ROW + self.ROW_GAP) + 4,
                                   1, KNOB_ROW - 8) for row, x in separators]
        # 줄 사이 가로 금. 손잡이가 놓인 데까지만 — 가장 오른쪽까지 보이는 손잡이의 끝에서 멈춘다(사용자).
        end = max(knob.rect.x + self.KNOB / 2 + knob.get_reach(gc, self.KNOB)
                  for knob in self.visible) if self.visible else body.x
        # 계기 줄이 있는 판(Auto Master)은 계기 아래 금이 판 끝까지 간다. 줄 사이 금도 거기에 맞춘다(사용자).
        if meter_separator:
            end = body.x + body.width
        self.separators += [wx.Rect(body.x, top + row * (KNOB_ROW + self.ROW_GAP) - self.RULE_GAP - 1,
                                    int(round(end - body.x)), 1) for row in range(1, rows)]
        self.separators += meter_separator

    def draw_body(self, gc):
        for rect in getattr(self, 'separators', ()):
            fill_rect(gc, RACK['line'], rect.x, rect.y, rect.width, rect.height)
        if self.meter_rect is not None:
            self.draw_meters(gc)
        if not self.knobs and self.data.get('path'):
            draw_text(gc, 'No parameters', self.body.x, self.body.y + self.body.height / 2 - 6,
                      8, RACK['faint'])


# ---------------------------------------------------------------- Custom


class CustomUnit(Unit):
    '''랙이 모르는 줄. 가져올 때 만났던 차례 그대로 끼워 둔다.'''

    def get_subtitle(self):
        count = len(self.data.get('lines', ()))
        return '%d line%s kept as written' % (count, '' if count == 1 else 's')

    def draw_body(self, gc):
        body = self.body
        lines = self.data.get('lines', ())
        font = wx.Font(8, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL,
                       faceName='Consolas')
        gc.SetFont(font, wx.Colour(RACK['dim']))
        y = body.y - 2
        for line in lines[:3]:
            gc.DrawText(fit_text(gc, line, body.width), body.x, y)
            y += 16
        if len(lines) > 3:
            gc.SetFont(get_font(8), wx.Colour(RACK['faint']))
            gc.DrawText('+%d more' % (len(lines) - 3), body.x, y)


UNIT_CLASSES = {
    'preamp': PreampUnit,
    'parametric': ParametricUnit,
    'graphic': GraphicUnit,
    'delay': DelayUnit,
    'stereo': StereoUnit,
    'vst': VstUnit,
    'custom': CustomUnit,
}


class AutoMasterUnit(VstUnit):
    '''PyWinAudio Auto Master. 속은 VST 장치 그대로지만 PyWinAudio 와 함께 깔리는 것이라 기본 장치처럼
    다룬다(사용자): 파일을 고르지 않고, 편집기가 없어 Edit·Choose 단추를 두지 않으며 그 자리까지
    손잡이가 쓴다. 이름과 색도 제 것.'''

    BUTTONS = 0
    # 예전 파라미터 이름 → 지금 이름들. 저장된 값은 새 이름 모두에 옮긴다(Stereo 하나가 둘로 나뉘었다).
    RENAMED = {'Stereo': ('Balance', 'Width Limit')}
    # 손잡이 → 그것을 켜고 끄는 단추. 단추가 꺼져 있으면 손잡이를 흐리게(사용자: 관계가 안 보였다).
    DEPENDS = {'Target': 'AGC', 'Max Gain': 'AGC', 'Speed': 'AGC', 'Max Width': 'Width Limit',
               'Wide Target': 'Mono Wide', 'Air': 'Mono Wide', 'Ceiling': 'Limiter'}

    def __init__(self, data, rack):
        self.rename_params(data)
        super().__init__(data, rack)
        self.face, self.accent = FACES['automaster']
        # 제 플러그인이라 가볍다. 켤 때 바로 올려 파라미터 목록을 지금 빌드에 맞춘다 — 늦게 올리면 새로
        # 생긴 손잡이(Air)가 판에도 엔진 설정 줄에도 없었다. 목록이 바뀌었으면 엔진 줄도 다시 쓴다.
        if os.path.exists(self.data.get('path') or '') and self.ensure_plugin() is not None:
            if [item[0] for item in self.data['params']] != self.loaded_names:
                wx.CallAfter(lambda: self.rack and self.rack.on_unit_change(self))

    loaded_names = None

    def rename_params(self, data):
        self.loaded_names = [item[0] for item in data.get('params') or []]
        params, renamed = [], False
        for name, value in data.get('params') or []:
            for new in self.RENAMED.get(name, (name,)):
                params.append([new, value])
            renamed |= name in self.RENAMED
        if renamed:
            data['params'] = params
            data.pop('defaults', None)
            data.pop('groups', None)
            data.pop('switches', None)

    def build(self):
        super().build()
        names = [item[0] for item in self.data.get('params', ())]
        for index, name in enumerate(names):
            switch = self.DEPENDS.get(name)
            if switch in names and index < len(self.knobs):
                at = names.index(switch)
                self.knobs[index].inactive = lambda at=at: self.data['params'][at][1] < 0.5
        # Analyzer 의 구역 단추처럼: 계기와 상세 설정을 따로 보이고 숨긴다. 둘 다 끌 수는 없다.
        # 모양·자리 모두 Analyzer 의 구역 칩과 같게: 제목 바로 뒤의 작은 글씨 칩(사용자).
        self.meters_button = Chip('Meters', lambda: self.toggle_part('show_meters'),
                                  lambda: self.data.get('show_meters', True),
                                  tip='Show or hide the meters')
        self.controls_button = Chip('Controls', lambda: self.toggle_part('show_controls'),
                                    lambda: self.data.get('show_controls', True),
                                    tip='Show or hide the detailed settings')
        self.chips = [self.meters_button, self.controls_button]
        self.extras = []
        self.subtitle_left = None

    def get_controls(self):
        # 칩은 접어도 이름 띠에 남아 누를 수 있다(Analyzer 처럼).
        return super().get_controls() + self.chips

    def layout(self, gc, rect):
        super().layout(gc, rect)
        left = self.power.rect.x + 22
        set_font(gc, TITLE_SIZE, RACK['text'], bold=True)
        x = left + gc.GetTextExtent(self.get_title().upper())[0] + 14
        middle = rect.y + FOLDED // 2
        for chip in self.chips:
            width = get_chip_width(gc, chip.caption)
            chip.rect = wx.Rect(int(x), middle - CHIP_HEIGHT // 2, width, CHIP_HEIGHT)
            x += width + CHIP_GAP
        self.subtitle_left = x - CHIP_GAP + 12

    def draw(self, gc):
        # 제목은 그대로, 부제는 칩 뒤에 쓴다.
        subtitle = self.get_subtitle()
        self.get_subtitle = lambda: ''
        try:
            super().draw(gc)
        finally:
            del self.get_subtitle
        if subtitle and self.subtitle_left is not None:
            tone = self.get_subtitle_tone()
            set_font(gc, 8, tone)
            limit = max(0, self.header_right - self.subtitle_left)
            draw_text(gc, fit_text(gc, subtitle, limit), self.subtitle_left,
                      self.rect.y + HEADER_BAND / 2 - 6, 8, tone, engraved=True)

    def toggle_part(self, key):
        other = 'show_controls' if key == 'show_meters' else 'show_meters'
        shown = not self.data.get(key, True)
        self.data[key] = shown
        if not shown and not self.data.get(other, True):
            self.data[other] = True
        self.rack.on_unit_change(self)

    def get_title(self):
        return 'Auto Master'

    def get_subtitle(self):
        if self.data.get('error'):
            return self.data['error']
        if self.notice:
            return self.notice
        if not os.path.exists(self.data.get('path') or AUTOMASTER_PATH):
            return 'Not installed: run plugin\\install.ps1'
        return 'AGC, stereo, limiter'

    def is_automaster(self):
        return True


def is_automaster_data(data):
    return data.get('kind') == 'vst' and os.path.basename(data.get('path') or '').lower() == AUTOMASTER_FILE


def migrate_automaster(data):
    '''Leveler 시절 칸이면 Auto Master 경로·이름으로 옮기고 참. 엔진 설정 줄도 다시 써야 한다.'''
    if data.get('kind') != 'vst' or os.path.basename(data.get('path') or '').lower() != OLD_AUTOMASTER_FILE:
        return False
    data['path'] = AUTOMASTER_PATH
    data['name'] = AUTOMASTER_NAME
    data.pop('defaults', None)
    return True


def build_unit(data, rack):
    if is_automaster_data(data):
        return AutoMasterUnit(data, rack)
    return UNIT_CLASSES.get(data['kind'], CustomUnit)(data, rack)


def clone(data):
    return copy.deepcopy(data)
