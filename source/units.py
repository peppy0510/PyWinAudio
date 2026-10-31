# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com
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
from rackui import mix
from rackui import set_font


# EAR + INSET is the left edge; the old names stay, summing to PAD
PAD = 14
EAR = 8
INSET = PAD - EAR
U = 40
FOLDED = 30
FOLD = 18
BODY_TOP = HEADER_BAND + 1 + PAD
BOTTOM = PAD
TIGHT_PAD = 6
# the 1 px rule under the header counts as space
TIGHT_TOP = TIGHT_PAD - 1
KNOB_ROW = 62
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
# audiodg (LocalService) must be able to read it; builds before the plugin store went here
OLD_AUTOMASTER_PATH = r'C:\Program Files\VSTPlugIns\PyWinAudio\PyWinAudioAutoMaster.dll'
AUTOMASTER_FAMILY = 'PyWinAudioAutoMaster'
AUTOMASTER_FILE = 'pywinaudioautomaster.dll'
AUTOMASTER_NAME = 'PyWinAudio Auto Master'
OLD_AUTOMASTER_FILE = 'pywinaudioleveler.dll'

BAND_TYPES = (('PK', 'Peak'), ('LSC', 'Low shelf'), ('HSC', 'High shelf'),
              ('HPQ', 'Low cut'), ('LPQ', 'High cut'))
GAIN_TYPES = ('PK', 'LSC', 'HSC')

SCREEN_RANGE = 18.0
GRAPHIC_RANGE = 12.0
MAX_FADERS = 31
MAX_BANDS = 20
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
        # the engine gets a plain VST line
        return {'kind': 'vst', 'on': True, 'path': get_automaster_path(), 'params': [], 'display': [],
                'chunk': None, 'name': AUTOMASTER_NAME, 'vendor': 'PyWinAudio'}
    return {'kind': 'custom', 'on': True, 'lines': []}


class Unit:

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
        return []

    def get_height(self, width):
        return FOLDED if self.folded else self.height

    def layout(self, gc, rect):
        self.rect = rect
        units = getattr(self.rack, 'units', [])
        if self in units:
            index = units.index(self)
            self.up.enabled = index > 0
            self.down.enabled = index < len(units) - 1
        # +6 puts the glyph ends 14 px in, like the fold glyph (measured)
        left, right = rect.x + EAR + INSET, rect.x + rect.width - EAR - INSET + 6
        middle = rect.y + FOLDED // 2
        self.fold.glyph = 'right' if self.folded else 'down'
        self.fold.tip = 'Unfold' if self.folded else 'Fold'
        self.fold.rect = wx.Rect(left - 5, middle - FOLD // 2, FOLD, FOLD)
        self.power.rect = wx.Rect(left + FOLD + 1, middle - 7, 14, 14)
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
        body = wx.Rect(left, rect.y + BODY_TOP, rect.x + rect.width - PAD - left,
                       rect.height - BODY_TOP - BOTTOM)
        self.body = body
        self.layout_body(gc, body)

    def layout_body(self, gc, body):
        pass

    def draw(self, gc):
        rect = self.rect
        draw_faceplate(gc, rect.x, rect.y, rect.width, rect.height, self.face, EAR, self.accent)
        left = self.power.rect.x + 21  # one less: the power icon sits 1 px right
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
    # with gc, pull the first knob so its visible left edge meets the area
    x = area.x
    if gc is not None and knobs:
        x -= max(0, int(width / 2 - knobs[0].get_reach(gc, width)))
    for knob in knobs:
        knob.rect = wx.Rect(x, area.y + (area.height - KNOB_ROW) // 2 - KNOB_TOP, width, KNOB_ROW + KNOB_TOP + 2)
        x += width + 4
    return x


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


class EqScreen(Control):

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
            draw_text(gc, f'{int(gain):+d}', inner.x - 4, y - 6, 7, RACK['lcd_text'],
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
    SIDE_BY_SIDE = 600
    SCREEN_HEIGHT = 136
    # measured: leaves 14 px below
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
                      0.1, 10.0, 0.71, lambda value: f'{value:.2f}', log=True,
                      ends=('.1', '10'))
        self.extras = [self.screen, self.previous, self.next, self.add, self.drop,
                       self.band_power, self.kind, self.freq, self.gain, self.q]

    def get_subtitle(self):
        count = len(self.data['bands'])
        return f'{count} band{"" if count == 1 else "s"}'

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
            # the screen rim (1 px outside) meets the body edge
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
        text = f'BAND {int(self.data.get("selected", 0) + 1)} / {count}' if count else 'NO BANDS'
        draw_text(gc, text, x, y, 8, RACK['text'], bold=True, align='center', engraved=True)


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
            return f'{count} bands'
        return f'{count} points, imported'

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
        # the 14 px above each slot is for the drag readout; lift the scale into it
        self.scale = wx.Rect(body.x, body.y, 26, body.height)
        area = wx.Rect(body.x + 30, body.y - 11, body.width - 30, body.height + 13)
        width = area.width / len(self.faders)
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
            draw_text(gc, f'{int(gain):+d}' if gain else '0', self.scale.x + 17, y - 6, 7,
                      RACK['dim'], align='right', engraved=True)


class DelayUnit(Unit):

    def build(self):
        self.time = Knob('TIME', lambda: self.data['ms'], self.put_time, 0.0, 300.0, 0.0,
                         lambda value: f'{value:.1f} ms', step=0.1, ends=('0', '300'))
        self.channel = Segment((('all', 'Both'), ('L', 'Left'), ('R', 'Right')),
                               lambda: self.data.get('channel', 'all'), self.put_channel)
        self.extras = [self.time, self.channel]

    def get_subtitle(self):
        channel = self.data.get('channel', 'all')
        return 'Both channels' if channel == 'all' else (f'{"Left" if channel == "L" else "Right"} '
                                                         'channel only')

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
    return f'{"R" if value > 0 else "L"} {round(abs(value) * 100)}%'


def get_width_text(value):
    return 'Mono' if value < 0.005 else f'{round(value * 100)}%'


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


class VstUnit(Unit):
    # plugins load on first touch; until then the saved names and values draw

    KNOB = 68
    KNOB_GAP = 4
    RULE_GAP = 12
    ROW_GAP = RULE_GAP * 2 + 1
    # counting rows (no gc) and placing them must agree
    BUTTONS = 76
    SEPARATOR = 21
    METER_ROW = 26
    METER_CELL = 112
    METER_GAP = 16
    METERS = (('agc', 'AGC', -12.0, 18.0, True), ('balance', 'BALANCE', -6.0, 6.0, True),
              ('side', 'WIDTH CUT', -6.0, 0.0, False), ('phase', 'PHASE', -2.0, 2.0, True),
              ('limiter', 'LIMITER', -12.0, 0.0, False), ('band0', 'LOW 150–600', -30.0, 0.0, False),
              ('band1', 'MID 600–3K', -30.0, 0.0, False), ('band2', 'HIGH 3K+', -30.0, 0.0, False))
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
        # older builds saved this notice as an error
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
        # VST2 parameters are 0..1 floats; ON/OFF display text marks a switch
        switches = self.data.get('switches') or []
        if index < len(switches) and switches[index] is not None:
            return bool(switches[index])
        display = self.data.get('display') or []
        text = display[index].strip().upper() if index < len(display) else ''
        return text in SWITCH_WORDS

    def get_short_name(self, name):
        return name.upper()

    def get_default(self, index):
        # defaults come from the freshly loaded plugin, before saved values go in
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
            return f'{self.plugin.get_display(index)} {self.plugin.get_label(index)}'
        display = self.data.get('display') or []
        if index < len(display) and display[index]:
            return display[index]
        return f'{round(value * 100)}%'

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
        display = [f'{plugin.get_display(index)} {plugin.get_label(index)}'
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
            # plugins may refuse a value or move others with it; read everything back
            self.read_state()
            if abs(self.data['params'][index][1] - value) > 0.01:
                self.show_notice(f'{self.get_short_name(self.data["params"][index][0])}: held by '
                                 'the plugin (another setting limits it)')
        self.changed()

    def on_edit(self):
        if self.editor:
            self.editor.Raise()
            return
        plugin = self.ensure_plugin()
        if plugin is None:
            return
        if not plugin.has_editor:
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
        start = os.path.dirname(self.data.get('path') or '') or self.rack.get_plugin_folder()
        with wx.FileDialog(self.rack, 'Choose a VST2 plugin', defaultDir=start,
                           wildcard='VST2 plugin or its download (*.dll;*.zip)|*.dll;*.zip',
                           style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as dialog:
            if dialog.ShowModal() != wx.ID_OK:
                return None
            path = dialog.GetPath()
        if not path.lower().endswith('.zip'):
            return path
        import pluginstore
        try:
            return pluginstore.install_zip(path)
        except Exception as error:
            self.show_notice(str(error) or 'Could not install the archive')
            self.rack.Refresh()
            return None

    def on_choose(self):
        path = self.pick_path()
        if path is None:
            return False
        old = self.data.get('path') or ''
        if old and os.path.basename(old).lower() == os.path.basename(path).lower():
            self.swap(path)
        else:
            self.load(path)
        import pluginstore
        pluginstore.clean(self.data.get('path'), [unit.data.get('path') for unit in self.rack.units
                                                  if unit.data['kind'] == 'vst'])
        return True

    def swap(self, path):
        # a newer build of the same plugin: saved values carry over by parameter name
        self.close()
        old = self.data['path']
        self.data['path'] = path
        self.data.pop('error', None)
        if self.ensure_plugin() is None:
            self.data['path'] = old
            self.rack.Refresh()
            return
        self.build()
        self.show_notice('Updated, settings kept')
        self.changed()

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
        # close the plugin's editor before its host window, or it touches a dead window
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
            if key.startswith('band'):
                self.draw_band_meter(gc, x, top, width, label, values, int(key[4:]), low, high)
                continue
            value = None if values is None else values.get('limiter_hold' if key == 'limiter' else key)
            fill = key.startswith('fill')
            if value is None:
                text = '--'
            elif fill and value <= low:
                text = 'off'
            elif key == 'phase':
                delay = '' if abs(value) < 0.05 else f'{value:+.1f} ms'
                text = ('INV ' + delay).strip() if values.get('phase_flip') else (delay or 'OK')
            else:
                shown = 0.0 if abs(value) < 0.05 else value  # no '-0.0'
                text = f'{shown:+.1f} dB' if bipolar else f'{min(0.0, shown):.1f} dB'
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
                    # bars from zero get a square start; a round one reads as an end
                    if bipolar and right - left > 2:
                        side = left if at >= zero else right - 2
                        fill_rect(gc, self.accent, side, bar.y, 2, bar.height)
            if bipolar:
                fill_rect(gc, RACK['dim'], zero, bar.y - 2, 1, bar.height + 4)

    def paint_levels(self, dc, offset, box=None):
        rect = wx.Rect(self.meter_rect).Inflate(2, 2)
        bitmap = wx.Bitmap(max(1, rect.width), max(1, rect.height))
        memory = wx.MemoryDC(bitmap)
        memory.SetBackground(wx.Brush(wx.Colour(RACK['panel'])))
        memory.Clear()
        gc = wx.GraphicsContext.Create(memory)
        gc.SetAntialiasMode(wx.ANTIALIAS_DEFAULT)
        gc.Translate(-rect.x, -rect.y)
        self.draw_meters(gc)
        del gc
        memory.SelectObject(wx.NullBitmap)
        dc.DrawBitmap(bitmap, rect.x, rect.y - offset)

    def draw_band_meter(self, gc, x, top, width, label, values, band, low, high):
        draw_text(gc, label, x, top, 7, RACK['dim'], bold=True)
        bar = wx.Rect(int(x), top + 17, int(width), 5)
        fill_rect(gc, RACK['track'], bar.x, bar.y, bar.width, bar.height, 2)
        bands = (values or {}).get('bands')
        if not bands:
            draw_text(gc, '--', x + width, top, 7, RACK['faint'], align='right')
            return
        info = bands[band]
        have = 10 ** (info['in'] / 10) if info['in'] > -100 else 0.0
        added = 10 ** (info['fill'] / 10) if info['fill'] > -100 else 0.0
        out = 10 * math.log10(have + added) if have + added > 1e-12 else -120.0
        to_x = lambda db: bar.x + bar.width * (min(max(db, low), high) - low) / (high - low)
        draw_text(gc, f'{out:.1f} dB' if out > low else 'mono', x + width, top, 7, RACK['text'], align='right')
        # a whole-pixel joint, so the two parts meet without an antialiased seam
        start, middle, end = bar.x, round(to_x(info['in'])), to_x(out)
        has_in, has_fill = middle - start >= 1, end - middle >= 1
        dim = mix(self.accent, RACK['track'], 0.55)
        if has_in:
            fill_rect(gc, dim, start, bar.y, middle - start, bar.height, 2)
        if has_fill:
            fill_rect(gc, self.accent, middle, bar.y, end - middle, bar.height, 2)
        # round corners where the parts meet leave a notch: square them off
        if has_in and has_fill:
            fill_rect(gc, dim, middle - min(2, middle - start), bar.y, min(2, middle - start),
                      bar.height)
            fill_rect(gc, self.accent, middle, bar.y, min(2, end - middle), bar.height)
        fill_rect(gc, RACK['text'], to_x(info['target']), bar.y - 2, 1, bar.height + 4)

    # resizes the editor window only
    HIDDEN = ('large gui',)

    def is_hidden(self, index):
        params = self.data.get('params') or []
        return index < len(params) and params[index][0].strip().lower() in self.HIDDEN

    def get_groups(self):
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
        return max(1, min(len(self.METERS), (body_width + self.METER_GAP) //
                          (self.METER_CELL + self.METER_GAP)))

    def get_meter_rows(self, body_width):
        return math.ceil(len(self.METERS) / self.get_meter_columns(body_width))

    def update_meters(self, elapsed):
        # the limiter jumps per block: hold its peak and release slowly
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
        # button rims show 1 px outside their cell
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
        # shift every row alike, or the columns misalign
        first = [self.knobs[index] for index, (row, x) in places.items() if x == 0]
        shift = 0
        if first:
            shift = max(0, int(self.KNOB / 2 - max(knob.get_reach(gc, self.KNOB)
                                                    for knob in first)))
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
        end = max(knob.rect.x + self.KNOB / 2 + knob.get_reach(gc, self.KNOB)
                  for knob in self.visible) if self.visible else body.x
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


class CustomUnit(Unit):

    def get_subtitle(self):
        count = len(self.data.get('lines', ()))
        return f'{count} line{"" if count == 1 else "s"} kept as written'

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
            gc.DrawText(f'+{len(lines) - 3} more', body.x, y)


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

    BUTTONS = 0
    # old parameter name -> new names; the value carries over to all
    RENAMED = {'Stereo': ('Balance', 'Width Limit')}
    # knob -> its switch; the knob draws dimmed while the switch is off
    DEPENDS = {'Target': 'AGC', 'Max Gain': 'AGC', 'Speed': 'AGC', 'Max Width': 'Width Limit',
               'Wide Target': 'Mono Wide', 'Air': 'Mono Wide', 'Ceiling': 'Limiter',
               'Drive': 'Limiter', 'Smooth': 'Limiter', 'Attack': 'Limiter'}
    # header chip -> the switches it turns off together; turning back on restores those that were on
    STAGES = {'Loudness': ('AGC', 'Limiter'),
              'Stereo': ('Balance', 'Phase Fix', 'Width Limit', 'Bass Mono', 'Mono Wide')}

    def __init__(self, data, rack):
        self.rename_params(data)
        super().__init__(data, rack)
        self.face, self.accent = FACES['automaster']
        # load at once so new parameters reach the plate and the engine line
        if os.path.exists(self.data.get('path') or '') and self.ensure_plugin() is not None:
            if [item[0] for item in self.data['params']] != self.loaded_names:
                wx.CallAfter(lambda: self.rack and self.rack.on_unit_change(self))

    loaded_names = None

    def is_bypassed(self):
        from automastermeter import READER
        return READER.get_bypass()

    def toggle_bypass(self):
        from automastermeter import READER
        if not READER.set_bypass(not READER.get_bypass()):
            self.show_notice('Play something first: the engine has not started Auto Master yet')
        if self.rack:
            self.rack.Refresh()

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
        self.meters_button = Chip('Meters', lambda: self.toggle_part('show_meters'),
                                  lambda: self.data.get('show_meters', True),
                                  tip='Show or hide the meters', glyph='meters')
        self.controls_button = Chip('Controls', lambda: self.toggle_part('show_controls'),
                                    lambda: self.data.get('show_controls', True),
                                    tip='Show or hide the detailed settings', glyph='controls')
        self.stage_buttons = [
            Chip('Loudness', lambda: self.toggle_stage('Loudness'),
                 lambda: self.is_stage_on('Loudness'), tip='Turn AGC and the limiter on or off',
                 glyph='loudness'),
            Chip('Stereo', lambda: self.toggle_stage('Stereo'),
                 lambda: self.is_stage_on('Stereo'),
                 tip='Turn balance, width and mono fill on or off', glyph='stereo')]
        # bypass goes through shared memory: instant, and never saved
        self.bypass_button = Chip('Bypass', self.toggle_bypass, self.is_bypassed,
                                  tip='Compare with the original at the same loudness (A/B)',
                                  glyph='bypass')
        self.chips = [self.meters_button, self.controls_button] + self.stage_buttons + [
            self.bypass_button]
        self.shown_chips = self.chips
        self.extras = []
        self.subtitle_left = None

    def get_controls(self):
        return super().get_controls() + self.shown_chips

    def layout(self, gc, rect):
        super().layout(gc, rect)
        left = self.power.rect.x + 21  # one less: the power icon sits 1 px right
        set_font(gc, TITLE_SIZE, RACK['text'], bold=True)
        x = left + gc.GetTextExtent(self.get_title().upper())[0] + 14
        middle = rect.y + FOLDED // 2
        # Meters and Controls change nothing while folded
        chips = self.chips[2:] if self.folded else self.chips
        self.shown_chips = chips
        for chip in chips:
            width = chip.get_width(gc)
            chip.rect = wx.Rect(int(x), middle - CHIP_HEIGHT // 2, width, CHIP_HEIGHT)
            x += width + CHIP_GAP
        self.subtitle_left = x - CHIP_GAP + 12

    def draw(self, gc):
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
            subtitle = fit_text(gc, subtitle, limit)
            # a lone ellipsis says nothing
            if subtitle != '…':
                draw_text(gc, subtitle, self.subtitle_left,
                          self.rect.y + HEADER_BAND / 2 - 6, 8, tone, engraved=True)

    def get_stage_switches(self, stage):
        names = [item[0] for item in self.data.get('params', ())]
        return [names.index(name) for name in self.STAGES[stage] if name in names]

    def is_stage_on(self, stage):
        return any(self.data['params'][index][1] >= 0.5 for index in self.get_stage_switches(stage))

    def toggle_stage(self, stage):
        switches = self.get_stage_switches(stage)
        if not switches:
            return
        params = self.data['params']
        remembered = self.data.setdefault('stages', {})
        if self.is_stage_on(stage):
            remembered[stage] = [params[index][0] for index in switches if params[index][1] >= 0.5]
            wanted = []
        else:
            wanted = remembered.pop(stage, None) or self.STAGES[stage]
        plugin = self.ensure_plugin()
        for index in switches:
            value = 1.0 if params[index][0] in wanted else 0.0
            params[index][1] = value
            if plugin is not None and index < plugin.count:
                plugin.set_value(index, value)
        if plugin is not None:
            self.read_state()
        self.changed()

    def put_param(self, index, value):
        # a switch set by hand makes the remembered set stale
        name = self.data['params'][index][0]
        for stage, names in self.STAGES.items():
            if name in names:
                self.data.get('stages', {}).pop(stage, None)
        super().put_param(index, value)

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
        if not os.path.exists(self.data.get('path') or get_automaster_path()):
            return 'Not installed: run plugin\\install.ps1'
        return 'AGC, stereo, limiter'

    def is_automaster(self):
        return True


def is_automaster_data(data):
    return data.get('kind') == 'vst' and os.path.basename(data.get('path') or '').lower() == AUTOMASTER_FILE


def get_automaster_path():
    import pluginstore
    return pluginstore.get_latest(AUTOMASTER_FAMILY, 'PyWinAudioAutoMaster.dll') or OLD_AUTOMASTER_PATH


def migrate_automaster(data):
    # the renamed Leveler, or an older build: point at the newest one, values carry over by name
    path = os.path.basename(data.get('path') or '').lower()
    if data.get('kind') != 'vst' or path not in (OLD_AUTOMASTER_FILE, AUTOMASTER_FILE):
        return False
    latest = get_automaster_path()
    if path == AUTOMASTER_FILE and (not os.path.exists(latest) or
                                    os.path.normcase(latest) == os.path.normcase(data['path'])):
        return False
    data['path'] = latest
    data['name'] = AUTOMASTER_NAME
    data.pop('defaults', None)
    return True


def build_unit(data, rack):
    if is_automaster_data(data):
        return AutoMasterUnit(data, rack)
    return UNIT_CLASSES.get(data['kind'], CustomUnit)(data, rack)


def clone(data):
    return copy.deepcopy(data)
