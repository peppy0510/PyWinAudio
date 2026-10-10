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
from rackui import RACK
from rackui import Button
from rackui import Control
from rackui import Fader
from rackui import IconButton
from rackui import Knob
from rackui import Power
from rackui import Segment
from rackui import draw_faceplate
from rackui import draw_lcd
from rackui import draw_text
from rackui import fill_rect
from rackui import fit_text
from rackui import get_font
from rackui import get_pen
from rackui import get_db_text
from rackui import get_hz_text
from rackui import get_short_hz
from rackui import set_font


EAR = 24
U = 40
NAME_WIDTH = 170
# 장치 폭이 이보다 좁으면 이름판을 왼쪽이 아니라 위쪽 띠로 올리고 조작부를 그 아래에 둔다.
NARROW = 560
STACK_GAIN = 34
INSET = 12

TITLES = {
    'preamp': 'Preamp',
    'parametric': 'Parametric EQ',
    'graphic': 'Graphic EQ',
    'delay': 'Delay',
    'stereo': 'Stereo',
    'vst': 'VST plugin',
    'custom': 'Custom lines',
}

ADDABLE = ('preamp', 'parametric', 'graphic', 'delay', 'stereo', 'vst')

BAND_TYPES = (('PK', 'Peak'), ('LSC', 'Low shelf'), ('HSC', 'High shelf'),
              ('HPQ', 'Low cut'), ('LPQ', 'High cut'))
GAIN_TYPES = ('PK', 'LSC', 'HSC')

SCREEN_RANGE = 18.0
GRAPHIC_RANGE = 12.0
MAX_FADERS = 31
MAX_BANDS = 20


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
    return {'kind': 'custom', 'on': True, 'lines': []}


class Unit:

    height = 2 * U
    tall = False
    stacked = False

    def __init__(self, data, rack):
        self.data = data
        self.rack = rack
        self.rect = wx.Rect()
        self.face, self.accent = FACES.get(data['kind'], FACES['custom'])
        self.power = Power(lambda: self.data.get('on', True), self.set_on)
        self.up = IconButton('up', lambda: rack.move(self, -1), tip='Move up')
        self.down = IconButton('down', lambda: rack.move(self, 1), tip='Move down')
        # 묻지 않고 곧장 뺀다. 빠진 자리에 되돌리기 띠가 남는다.
        self.remove = IconButton('close', lambda: rack.remove(self), tip='Remove')
        self.extras = []
        self.build()

    def build(self):
        pass

    def get_controls(self):
        return [self.power, self.up, self.down, self.remove] + self.extras

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
        '''좁으면 키가 작은 장치도 위쪽 띠를 얹는다. 그만큼 키가 자란다.'''
        if not self.tall and width < NARROW:
            return self.height + STACK_GAIN
        return self.height

    def layout(self, gc, rect):
        self.rect = rect
        self.stacked = self.tall or rect.width < NARROW
        left, right = rect.x + EAR + INSET, rect.x + rect.width - EAR - INSET + 2
        if self.stacked:
            top = rect.y + 9
            self.power.rect = wx.Rect(left, top + 2, 14, 14)
            x = right
            for button in (self.remove, self.down, self.up):
                x -= IconButton.SIZE
                button.rect = wx.Rect(x, top, IconButton.SIZE, IconButton.SIZE)
                x -= 3
            x -= 8
            for button in reversed(self.get_header_buttons()):
                width = button.get_width(gc)
                x -= width
                button.rect = wx.Rect(x, top - 2, width, Button.HEIGHT)
                x -= 6
            self.header_right = x
            body = wx.Rect(left, rect.y + 38, right - left, rect.height - 38 - 12)
        else:
            middle = rect.y + rect.height / 2
            self.power.rect = wx.Rect(left, round(middle - 7), 14, 14)
            x = right - IconButton.SIZE
            for index, button in enumerate((self.up, self.down, self.remove)):
                button.rect = wx.Rect(x, rect.y + 8 + index * (IconButton.SIZE + 4),
                                      IconButton.SIZE, IconButton.SIZE)
            self.header_right = left + NAME_WIDTH - 8
            body = wx.Rect(left + NAME_WIDTH, rect.y + 8,
                           x - 14 - left - NAME_WIDTH, rect.height - 16)
        self.body = body
        self.layout_body(gc, body)

    def layout_body(self, gc, body):
        pass

    def draw(self, gc):
        rect = self.rect
        draw_faceplate(gc, rect.x, rect.y, rect.width, rect.height, self.face, EAR)
        left = self.power.rect.x + 22
        limit = max(0, self.header_right - left)
        if self.stacked:
            top = rect.y + 8
            set_font(gc, 10.5, RACK['text'], bold=True)
            title = fit_text(gc, self.get_title().upper(), limit)
            width = draw_text(gc, title, left, top, 10.5, RACK['text'], bold=True,
                              engraved=True)[0]
            set_font(gc, 8, RACK['dim'])
            subtitle = fit_text(gc, self.get_subtitle(), max(0, limit - width - 12))
            draw_text(gc, subtitle, left + width + 12, top + 3, 8,
                      self.get_subtitle_tone(), engraved=True)
            fill_rect(gc, '#000000', rect.x + EAR + 6, rect.y + 32,
                      rect.width - EAR * 2 - 12, 1)
            fill_rect(gc, '#ffffff', rect.x + EAR + 6, rect.y + 33,
                      rect.width - EAR * 2 - 12, 1)
        else:
            middle = rect.y + rect.height / 2
            set_font(gc, 10.5, RACK['text'], bold=True)
            title = fit_text(gc, self.get_title().upper(), limit)
            draw_text(gc, title, left, middle - 17, 10.5, RACK['text'], bold=True,
                      engraved=True)
            set_font(gc, 8, RACK['dim'])
            subtitle = fit_text(gc, self.get_subtitle(), limit)
            draw_text(gc, subtitle, left, middle + 2, 8, self.get_subtitle_tone(),
                      engraved=True)
        gc.Clip(rect.x, rect.y, rect.width, rect.height)
        self.draw_body(gc)
        for control in self.get_controls():
            control.draw(gc, self.accent)
        gc.ResetClip()

    def draw_body(self, gc):
        pass


def place_knobs(knobs, area, width=58):
    '''손잡이를 왼쪽부터 같은 폭으로 늘어놓고 끝 x 를 돌려준다.'''
    x = area.x
    for knob in knobs:
        knob.rect = wx.Rect(x, area.y + (area.height - 64) // 2, width, 64)
        x += width + 4
    return x


# ---------------------------------------------------------------- Preamp


class PreampUnit(Unit):

    def build(self):
        self.gain = Knob('GAIN', lambda: self.data['gain'], self.put_gain, -30.0, 12.0, 0.0,
                         get_db_text, bipolar=False, step=0.1)
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
        x = place_knobs([self.gain], body)
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
            draw_text(gc, str(index + 1), x, y - 6, 7, '#0b141c' if lit else colour,
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

    height = 5 * U + 8
    tall = True
    PANEL = 236
    # 이보다 좁으면 화면을 위에, 밴드 조작부를 그 아래에 둔다.
    SIDE_BY_SIDE = 600
    SCREEN_HEIGHT = 136
    PANEL_HEIGHT = 134

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
                         20.0, 20000.0, 1000.0, get_hz_text, log=True)
        self.gain = Knob('GAIN', lambda: self.get_value('gain', 0.0),
                         lambda value: self.put_value('gain', round(value, 1)),
                         -SCREEN_RANGE, SCREEN_RANGE, 0.0, get_db_text, bipolar=True)
        self.q = Knob('Q', lambda: self.get_value('q', 1.0),
                      lambda value: self.put_value('q', round(value, 2)),
                      0.1, 10.0, 0.71, lambda value: '%.2f' % value, log=True)
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
        if width < self.SIDE_BY_SIDE:
            return 38 + self.SCREEN_HEIGHT + 10 + self.PANEL_HEIGHT + 12
        return self.height

    def layout_body(self, gc, body):
        if self.rect.width < self.SIDE_BY_SIDE:
            panel = min(self.PANEL + 40, body.width)
            self.screen.rect = wx.Rect(body.x, body.y + 2, body.width, self.SCREEN_HEIGHT)
            x = body.x
            top = body.y + self.SCREEN_HEIGHT + 12
        else:
            panel = min(self.PANEL, body.width // 2)
            self.screen.rect = wx.Rect(body.x, body.y + 2, body.width - panel - 16,
                                       body.height - 4)
            x = body.x + body.width - panel
            top = body.y + 2
        self.band_power.rect = wx.Rect(x, top + 4, 14, 14)
        self.previous.rect = wx.Rect(x + 22, top + 2, IconButton.SIZE, IconButton.SIZE)
        self.band_label = (x + 22 + IconButton.SIZE + 34, top + 4)
        self.next.rect = wx.Rect(x + 22 + IconButton.SIZE + 68, top + 2, IconButton.SIZE,
                                 IconButton.SIZE)
        right = x + panel
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

    height = 4 * U + 8
    tall = True

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
        self.scale = wx.Rect(body.x, body.y, 26, body.height)
        area = wx.Rect(body.x + 30, body.y, body.width - 30, body.height)
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
            fill_rect(gc, '#000000' if gain else RACK['faint'], self.scale.x + 18, y,
                      self.body.width - 18, 1)
            draw_text(gc, '%+d' % gain if gain else '0', self.scale.x + 14, y - 6, 7,
                      RACK['dim'], align='right', engraved=True)


# ---------------------------------------------------------------- Delay · Stereo


class DelayUnit(Unit):

    def build(self):
        self.time = Knob('TIME', lambda: self.data['ms'], self.put_time, 0.0, 300.0, 0.0,
                         lambda value: '%.1f ms' % value, step=0.1)
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
        x = place_knobs([self.time], body)
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
                            -1.0, 1.0, 0.0, get_balance_text, bipolar=True)
        self.width = Knob('WIDTH', lambda: self.data['width'],
                          lambda value: self.put('width', round(value, 2)),
                          0.0, 2.0, 1.0, get_width_text, bipolar=True)
        self.swap = Button('Swap L/R', lambda: self.put('swap', not self.data.get('swap')),
                           active=lambda: bool(self.data.get('swap')))
        self.extras = [self.balance, self.width, self.swap]

    def get_subtitle(self):
        return 'Balance, width, swap'

    def put(self, key, value):
        self.data[key] = value
        self.changed()

    def layout_body(self, gc, body):
        x = place_knobs([self.balance, self.width], body)
        width = self.swap.get_width(gc)
        self.swap.rect = wx.Rect(x + 12, body.y + (body.height - Button.HEIGHT) // 2,
                                 width, Button.HEIGHT)


# ---------------------------------------------------------------- VST


class VstUnit(Unit):
    '''플러그인은 손을 댈 때에야 이 프로세스에 올린다. 그 전에는 저장해 둔 이름과
    값으로 그린다 — 앱을 켤 때마다 남의 DLL 을 모두 올릴 까닭이 없다.'''

    KNOB = 58

    plugin = None
    editor = None

    def build(self):
        '''이름이 바뀌면 손잡이를 다시 만든다. 올려 둔 플러그인과 편집기는 그대로 둔다.'''
        self.edit = Button('Edit', self.on_edit)
        self.choose = Button('Choose…', self.on_choose)
        self.knobs = []
        for index, item in enumerate(self.data.get('params', ())):
            self.knobs.append(Knob(
                self.get_short_name(item[0]),
                lambda index=index: self.data['params'][index][1],
                lambda value, index=index: self.put_param(index, value),
                0.0, 1.0, self.get_default(index),
                lambda value, index=index: self.get_display(index, value)))
        self.visible = []
        self.extras = [self.edit, self.choose]

    def get_controls(self):
        return super().get_controls() + self.visible

    def get_short_name(self, name):
        return name.upper()

    def get_default(self, index):
        return self.data['params'][index][1]

    def get_title(self):
        return self.data.get('name') or 'VST plugin'

    def get_subtitle(self):
        if self.data.get('error'):
            return self.data['error']
        if not self.data.get('path'):
            return 'Choose a plugin file'
        if not os.path.exists(self.data['path']):
            return 'Plugin file not found'
        return self.data.get('vendor') or os.path.basename(self.data['path'])

    def get_subtitle_tone(self):
        path = self.data.get('path')
        if self.data.get('error') or (path and not os.path.exists(path)):
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
            if plugin.uses_chunks:
                self.data['chunk'] = plugin.get_chunk()
        self.changed()

    def on_edit(self):
        if self.editor:
            self.editor.Raise()
            return
        plugin = self.ensure_plugin()
        if plugin is None:
            return
        if not plugin.has_editor:
            self.data['error'] = 'This plugin has no editor of its own'
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

    def on_choose(self):
        start = os.path.dirname(self.data.get('path') or '') or self.rack.get_plugin_folder()
        with wx.FileDialog(self.rack, 'Choose a VST2 plugin', defaultDir=start,
                           wildcard='VST2 plugin (*.dll)|*.dll',
                           style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as dialog:
            if dialog.ShowModal() != wx.ID_OK:
                return False
            path = dialog.GetPath()
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

    def layout_body(self, gc, body):
        width = max(self.edit.get_width(gc), self.choose.get_width(gc))
        right = body.x + body.width
        middle = body.y + (body.height - Button.HEIGHT * 2 - 6) // 2
        self.edit.rect = wx.Rect(right - width, middle, width, Button.HEIGHT)
        self.choose.rect = wx.Rect(right - width, middle + Button.HEIGHT + 6, width,
                                   Button.HEIGHT)
        path = self.data.get('path')
        self.edit.enabled = bool(path and os.path.exists(path))
        room = body.width - width - 12
        count = max(0, min(len(self.knobs), room // (self.KNOB + 4)))
        self.visible = self.knobs[:count]
        place_knobs(self.visible, body, width=self.KNOB)
        self.hidden = len(self.knobs) - count
        self.more = (body.x + count * (self.KNOB + 4) + 4, body.y + body.height / 2 - 6)

    def draw_body(self, gc):
        if self.hidden > 0 and self.visible:
            draw_text(gc, '+%d' % self.hidden, *self.more, 8, RACK['dim'], engraved=True)
        elif not self.knobs and self.data.get('path'):
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
        y = body.y + 6
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


def build_unit(data, rack):
    return UNIT_CLASSES.get(data['kind'], CustomUnit)(data, rack)


def clone(data):
    return copy.deepcopy(data)
