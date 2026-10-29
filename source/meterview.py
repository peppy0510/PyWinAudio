# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com
'''


import bisect
import collections
import math
import threading
import time
import wx

import numpy

from meter import RATE
from meter import Capture
from meter import LOUDNESS_FLOOR
from meter import to_db
from rackui import FACES
from rackui import HEADER_BAND
from rackui import RACK
from rackui import TITLE_SIZE
from rackui import draw_faceplate
from rackui import draw_lcd
from rackui import draw_rails
from rackui import draw_text
from rackui import draw_title
from rackui import fill_rect
from rackui import get_font
from rackui import get_pen
from rackui import get_short_hz
from rackui import mix
from rackui import draw_glyph
from rackui import CHIP_GAP
from rackui import CHIP_HEIGHT
from rackui import CHIP_PAD
from rackui import CHIP_TEXT
from rackui import draw_chip
from rackui import get_chip_width
from units import EAR
from units import FOLD
from units import FOLDED
from units import PAD
from units import TIGHT_PAD
from units import TIGHT_TOP
from utilities import CONTROL_ACCENT
from utilities import call_painted


# reads as continuous, and a quarter less CPU than 40
FPS = 30
MARGIN = 8
PARTS = ('level', 'spectrum', 'oscilloscope', 'spectrogram')
TITLE = 'Analyzer'
PART_LABELS = {'level': 'METERS', 'spectrum': 'SPECTRUM', 'oscilloscope': 'SCOPE',
               'spectrogram': 'SPECTROGRAM'}
SHORT_LABELS = {'level': 'METERS', 'spectrum': 'SPEC', 'oscilloscope': 'SCOPE', 'spectrogram': 'GRAM'}
PART_BODIES = {'level': 118, 'spectrum': 118, 'oscilloscope': 118, 'spectrogram': 118}
LCD_PAD = 8
PIN = 18
PIN_WIDTH = 30

FLOOR = -60.0
PEAK_FALL = 24.0
HOLD_TIME = 1.5
HOLD_FALL = 30.0

FFT_SIZE = 8192
SPECTRUM_FLOOR = -90.0
SPECTRUM_FALL = 40.0
# +3 dB per octave around 1 kHz so music reads flat
SPECTRUM_TILT = 3.0
SPECTRUM_SMOOTH = 0.35
PEAK_LINE_HOLD = 1.0
PEAK_LINE_FALL = 12.0
SPECTRUM_FREQS = (20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000)
SPECTRUM_DBS = (0, -12, -24, -36, -48, -60, -72, -84)
SCOPE_SAMPLES = 1536

GRAM_LOW = -84.0
GRAM_HIGH = -12.0
# inferno: brightness only rises, so red-green colour blindness still reads it
GRAM_STOPS = ((0.0, '#111215'), (0.125, '#1f0c48'), (0.25, '#57106e'), (0.375, '#8a226a'),
              (0.5, '#bc3754'), (0.625, '#e45a31'), (0.75, '#f98e09'), (0.875, '#f6d746'),
              (1.0, '#fcffa4'))
GRAM_FREQS = (100, 1000, 10000)

# 75 ms read as bytes of 16-bit stereo: 900 samples at 48 kHz
BAR_FRAME = int(RATE * 0.075 / 4)
BAR_POINTS = int(RATE * 0.1)
BAR_LOW_PAD = (2, 3, 4, 5, 6, 7)
BAR_NOTES = [8.0, 8.41536811017449] + [8.91577193817796 * 2 ** (step / 12)
                                       for step in range(127)]
BAR_HEIGHT = 0.4
# zero-padded bins alternate peak and trough, so low bars read their neighbours too
BAR_REACH = 3
# autogain = 0.14 / (3 RMS above 5 kHz), followed live
AUTOGAIN_DEFAULT = 0.4
AUTOGAIN_RANGE = (0.05, 4.0)
AUTOGAIN_FOLLOW = 2.0


def get_firwin(taps, cutoff, highpass):
    # scipy.signal.firwin (Hamming) without scipy
    middle = numpy.arange(taps) - (taps - 1) / 2
    if highpass:
        response = numpy.sinc(middle) - cutoff * numpy.sinc(cutoff * middle)
    else:
        response = cutoff * numpy.sinc(cutoff * middle)
    response *= numpy.hamming(taps)
    return response / (response * numpy.cos(numpy.pi * middle * (1.0 if highpass else 0.0))).sum()


def get_autogain_weights():
    nyquist = RATE / 2
    freqs = numpy.arange(1, BAR_POINTS // 2) * (RATE / BAR_POINTS)

    def respond(taps, cutoff, highpass):
        coefficients = get_firwin(taps, cutoff / nyquist, highpass)
        phase = numpy.exp(-2j * numpy.pi * numpy.outer(freqs / RATE, numpy.arange(taps)))
        return phase @ coefficients

    chain = (respond(15, 500, True) * respond(7, 1000, True) * respond(5, 1000, True) *
             respond(5, 5000, True))
    if nyquist > 21000:
        chain = chain * respond(45, 20000, False)
        chain = chain + chain * respond(5, 15000, True) * 0.5
    return numpy.abs(chain) ** 2


AUTOGAIN_WEIGHTS = get_autogain_weights()
BAR_SET = 103
BAR_PITCH = 3
BAR_WIDTH = 1
SCOPE_PERSIST = 0.55
SCOPE_DOT = 0.30

LOW = '#4c9aff'
METER_BLUE = '#d2e6ff'
TRACE_BLUE = '#a3cbff'
BAR_COLOUR = METER_BLUE
MID = '#ffb04d'
HIGH = '#ff7a33'
CLIP = '#ff7a33'
METER_MID = '#ffc47a'
METER_HIGH = '#ff8e52'
SEGMENT_OFF = 0.84
SEGMENT_HALF = 0.0
BAR = 6
ROW = 12
METER_FLOOR = -48.0
METER_SCALE = (0, -3, -6, -9, -12, -18, -24, -30, -36, -42, -48)
SEGMENT = 1
SEGMENT_GAP = 2
NAME_WIDTH = 12
CLIP_GAP = 4
CLIP_WIDTH = 4
NAME_GAP = 4
READOUT = 34
LOUDNESS_NAMES = {'M': 'MOM', 'S': 'SHORT', 'I': 'INT'}
PHASE_NAMES = {'correlation': 'CORR', 'balance': 'BAL'}
STRIP_HEIGHT = 24
SCOPE_SIDE = 104
BALANCE_RANGE = 6.0
LOUDNESS_COLOURS = {'M': '#4c9aff', 'S': '#8cc8ff', 'I': '#ffb04d'}
READOUT_FONT = 'Consolas'
LOUDNESS_EVERY = 0.5
NOTE_NAMES = ('C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B')

# plain geometry for the analysis thread, which must not touch wx objects
Box = collections.namedtuple('Box', 'x y width height')


def get_rgb(code):
    return [int(code[index:index + 2], 16) for index in (1, 3, 5)]


def get_gram_colours():
    stops = [(at, numpy.array(get_rgb(tone), dtype='float64')) for at, tone in GRAM_STOPS]
    table = numpy.zeros((256, 3), dtype='uint8')
    for index in range(256):
        ratio = index / 255
        for (a, ca), (b, cb) in zip(stops, stops[1:]):
            if ratio <= b:
                table[index] = ca + (cb - ca) * ((ratio - a) / max(b - a, 1e-9))
                break
    return table


GLOW_BASE = numpy.array(get_rgb(RACK['lcd']), dtype='float32')
GLOW_DOT = numpy.array(get_rgb(TRACE_BLUE), dtype='float32')


class Pacer(threading.Thread):
    # wx.Timer snaps to the 15.6 ms tick; a thread paces frames evenly

    def __init__(self, view):
        super().__init__(name='meter-pacer', daemon=True)
        self.view = view
        self.running = True
        self.pending = False

    def run(self):
        interval = 1.0 / FPS
        target = time.perf_counter()
        while self.running:
            target += interval
            delay = target - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
            else:
                target = time.perf_counter()
            if not self.pending:
                view = self.view
                if view.wanted:
                    with view.lock:
                        if self.running:
                            view.analyze()
                self.pending = True
                try:
                    call_painted(view, view.tick)
                except Exception:
                    return


BRUSHES = {}
MONO = {}


def get_mono(size):
    if size not in MONO:
        MONO[size] = wx.Font(wx.FontInfo(size).FaceName(READOUT_FONT).Bold())
    return MONO[size]


def get_brush(colour):
    if colour not in BRUSHES:
        BRUSHES[colour] = wx.Brush(wx.Colour(colour))
    return BRUSHES[colour]


class MeterView(wx.Panel):

    def __init__(self, parent, on_change, folded=False, pinned=True, parts=None):
        super().__init__(parent, style=wx.FULL_REPAINT_ON_RESIZE)
        # no SetDoubleBuffered: WS_EX_COMPOSITED recomposites the rack every frame
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.on_change = on_change
        self.capture = Capture()
        self.pacer = None
        self.background = None
        self.background_key = None
        self.last = time.perf_counter()
        self.peak = [FLOOR, FLOOR]
        self.hold = [FLOOR, FLOOR]
        self.held_at = [0.0, 0.0]
        self.rms = [FLOOR, FLOOR]
        self.clips = [False, False]
        self.spectrum = None
        self.spectrum_hold = None
        self.bars = None
        self.bar_bins = None
        self.bar_weights = None
        self.bars_bitmap = None
        self.lit = None
        self.autogain = AUTOGAIN_DEFAULT
        self.scope = None
        self.scope_glow = None
        self.scope_gain = 1.0
        self.wave = None
        self.wave_dark = 0
        self.wave_pushed = 0
        self.wave_image = None
        self.wave_source = None
        self.wave_bitmap = None
        self.gram = None
        self.gram_rows = None
        self.gram_dark = 0
        self.gram_serial = 0
        self.gram_drawn = 0
        self.gram_source = None
        self.gram_bitmap = None
        self.gram_colours = get_gram_colours()
        self.scope_bitmap = None
        self.scope_source = None
        self.spectrum_bins = None
        self.extents = {}
        self.chip_widths = {}
        self.lock = threading.Lock()
        self.geometry = {}
        self.wanted = False
        self.dirty = False
        self.frame_power = None
        self.correlation = 0.0
        self.balance = 0.0
        self.regions = {}
        self.window = numpy.hanning(FFT_SIZE).astype('float32')
        self.layout_width = None
        self.drawn_quiet = False
        self.loudness = (LOUDNESS_FLOOR, LOUDNESS_FLOOR, LOUDNESS_FLOOR)
        self.loudness_at = 0.0
        self.buffer = None
        self.hover = None

        self.Bind(wx.EVT_PAINT, self.on_paint)
        self.Bind(wx.EVT_ERASE_BACKGROUND, lambda event: None)
        self.Bind(wx.EVT_SIZE, self.on_size)
        self.Bind(wx.EVT_LEFT_DOWN, self.on_down)
        self.Bind(wx.EVT_MOTION, self.on_motion)
        self.Bind(wx.EVT_LEAVE_WINDOW, self.on_leave)
        self.Bind(wx.EVT_MOUSEWHEEL, self.on_wheel)
        self.folded = folded
        self.pinned = pinned
        self.parts = {name: bool((parts or {}).get(name)) for name in PARTS}
        if all(self.parts.values()):
            self.parts = {name: False for name in PARTS}
        self.right_margin = MARGIN
        self.left_margin = MARGIN
        self.flowing = False
        self.on_height = lambda: None
        if self.is_running():
            self.start()

    def is_running(self):
        return not self.folded and not all(self.parts.values())

    def is_open(self, name):
        return not self.folded and not self.parts[name]

    def set_part_hidden(self, name, folded):
        if self.parts[name] == folded:
            return
        if folded and all(self.parts[other] for other in PARTS if other != name):
            for other in PARTS:
                if other != name:
                    self.parts[other] = False
        self.parts[name] = folded
        self.start() if self.is_running() else self.stop()
        self.SetMinSize(wx.Size(-1, self.get_height(self.GetClientSize().width)))
        self.background_key = None
        with self.lock:
            if name == 'spectrum':
                self.spectrum = self.spectrum_hold = None
            elif name == 'level':
                self.scope = self.scope_glow = None
                self.bars = None
            elif name == 'oscilloscope':
                self.wave = None
            elif name == 'spectrogram':
                self.gram = None
        self.on_height()
        self.Refresh()
        self.on_change()

    def set_folded(self, folded):
        if folded == self.folded:
            return
        self.folded = folded
        self.start() if self.is_running() else self.stop()
        height = self.get_height(self.GetClientSize().width)
        self.SetMinSize(wx.Size(-1, height))
        self.background_key = None
        self.on_height()
        self.Refresh()
        self.on_change()

    def set_pinned(self, pinned):
        if pinned == self.pinned:
            return
        self.pinned = pinned
        self.background_key = None
        self.on_height()
        self.Refresh()
        self.on_change()

    def start(self):
        self.capture.start()
        if self.pacer is None:
            self.pacer = Pacer(self)
            self.pacer.start()

    def stop(self):
        if self.pacer is not None:
            self.pacer.running = False
            self.pacer = None
        self.capture.stop()
        with self.lock:
            self.clear()
        self.Refresh()

    def clear(self):
        self.peak = [FLOOR, FLOOR]
        self.hold = [FLOOR, FLOOR]
        self.rms = [FLOOR, FLOOR]
        self.clips = [False, False]
        self.spectrum = None
        self.spectrum_hold = None
        self.bars = None
        self.scope = None
        self.scope_glow = None
        self.scope_gain = 1.0
        self.wave = None
        self.gram = None
        self.correlation = 0.0
        self.balance = 0.0
        self.autogain = AUTOGAIN_DEFAULT
        self.drawn_quiet = False

    def close(self):
        if self.pacer is not None:
            self.pacer.running = False
            self.pacer = None
        self.capture.stop()

    def get_top(self):
        return MARGIN if self.pinned and not self.flowing else 0

    def get_height(self, width):
        top = self.get_top()
        shown = [name for name in PARTS if not self.parts[name]]
        if self.folded or not shown:
            return top + FOLDED
        return (top + HEADER_BAND + 1 + TIGHT_TOP + sum(PART_BODIES[name] for name in shown) +
                len(shown) - 1 + TIGHT_PAD)

    def on_size(self, event):
        width = self.GetClientSize().width
        height = self.get_height(width)
        if self.GetMinSize().height != height:
            self.SetMinSize(wx.Size(-1, height))
            wx.CallAfter(self.on_height)
        self.background_key = None
        event.Skip()

    def get_chip_width(self, text):
        # a DC measures 1 px off from the GC that draws the chip
        if text not in self.chip_widths:
            dc = wx.MemoryDC(wx.Bitmap(1, 1))
            self.chip_widths[text] = get_chip_width(wx.GraphicsContext.Create(dc), text)
        return self.chip_widths[text]

    def layout(self, width):
        plate = wx.Rect(self.left_margin, self.get_top(),
                        width - self.left_margin - self.right_margin,
                        self.get_height(width) - self.get_top())
        left = plate.x + PAD
        right = plate.x + plate.width - PAD
        middle = plate.y + FOLDED // 2
        regions = {'plate': plate, 'fold': wx.Rect(left - 5, middle - FOLD // 2, FOLD, FOLD),
                   'icon': wx.Rect(left + FOLD, middle - 7, 14, 14),
                   'pin': wx.Rect(plate.x + plate.width - TIGHT_PAD - 1 - PIN_WIDTH, middle - PIN // 2, PIN_WIDTH, PIN),
                   'clips': [], 'chips': {}}
        dc = wx.ScreenDC()
        dc.SetFont(get_font(TITLE_SIZE, bold=True))
        start = left + FOLD + 22 + dc.GetTextExtent(TITLE.upper())[0] + 14
        for labels in (PART_LABELS, SHORT_LABELS):
            x = start
            for name in PARTS:
                chip = self.get_chip_width(labels[name])
                regions['chips'][name] = wx.Rect(x, middle - CHIP_HEIGHT // 2, chip, CHIP_HEIGHT)
                x += chip + CHIP_GAP
            regions['chip_labels'] = labels
            if x - CHIP_GAP <= regions['pin'].x - 8:
                break
        regions['chips_end'] = x - CHIP_GAP
        self.regions = regions
        shown = [name for name in PARTS if not self.parts[name]]
        if self.folded or not shown:
            return regions
        # the screen rim is drawn 1 px outside
        top = HEADER_BAND + 1 + TIGHT_TOP
        body = wx.Rect(plate.x + TIGHT_PAD + 1, plate.y + top + 1,
                       plate.width - TIGHT_PAD * 2 - 2, plate.height - top - TIGHT_PAD - 2)
        regions['screen'] = body
        regions['dividers'] = []
        y = body.y
        sections = {}
        for index, name in enumerate(shown):
            if index:
                regions['dividers'].append(wx.Rect(body.x, y, body.width, 1))
                y += 1
            # share the rim's 2 px so equal sections stay equal
            trim = 2 // len(shown) + (1 if index < 2 % len(shown) else 0)
            height = PART_BODIES[name] - trim
            sections[name] = wx.Rect(body.x, y, body.width, height)
            y += height
        for name in ('spectrum', 'oscilloscope', 'spectrogram'):
            if name in sections:
                regions[name] = sections[name]
        if 'level' in sections:
            section = sections['level']
            names = 1 + LCD_PAD
            readout = (CLIP_GAP + CLIP_WIDTH + NAME_GAP + NAME_WIDTH + NAME_GAP + READOUT * 2 +
                       LCD_PAD)
            side = min(SCOPE_SIDE, section.height)
            wing = max(readout, side + names)
            regions['scope'] = wx.Rect(section.x + 4, section.y + (section.height - side) // 2 + 4,
                                       side - 8, side - 8)
            regions['scope_divider'] = wx.Rect(section.x + side, section.y + LCD_PAD, 1,
                                               section.height - LCD_PAD * 2)
            pitch = SEGMENT + SEGMENT_GAP
            x0 = section.x + wing
            x1 = section.x + section.width - wing
            count = max(1, (x1 - x0 + SEGMENT_GAP) // pitch)
            x0 += (x1 - x0 - (count * pitch - SEGMENT_GAP)) // 2
            x1 = x0 + count * pitch
            self.layout_level(regions, wx.Rect(section.x + side + 1, section.y,
                                               section.width - side - 1, section.height),
                              (x0, x1))
        return regions

    def layout_level(self, regions, body, span):
        regions['level'] = body
        inner = wx.Rect(body.x + LCD_PAD, body.y + LCD_PAD, body.width - LCD_PAD * 2,
                        body.height - LCD_PAD * 2)
        x0, x1 = span
        rows, boxes = {}, {}
        y = inner.y
        for key in ('L', 'R', None, 'M', 'S', 'I', '', 'C', 'B'):
            if key is None:
                regions['scale_y'] = y
                y += ROW + 4
                continue
            if key == '':
                y += 4
                continue
            rows[key] = wx.Rect(x0, y + (ROW - BAR) // 2, x1 - x0, BAR)
            y += ROW
        right = inner.x + inner.width
        for key in ('L', 'R'):
            row = rows[key]
            boxes[key + 'pk'] = wx.Rect(right - READOUT * 2, row.y - 3, READOUT, BAR + 6)
            boxes[key + 'rms'] = wx.Rect(right - READOUT, row.y - 3, READOUT, BAR + 6)
        for key in ('M', 'S', 'I', 'C', 'B'):
            row = rows[key]
            boxes[key] = wx.Rect(right - READOUT * 2, row.y - 3, READOUT, BAR + 6)
        regions['correlation'] = rows.pop('C')
        regions['balance'] = rows.pop('B')
        regions['phase_boxes'] = {'correlation': boxes.pop('C'), 'balance': boxes.pop('B')}
        top, bottom = rows['M'].y - 3, rows['I'].y + BAR + 3
        middle = (top + bottom) // 2
        regions['strip'] = wx.Rect(x0 - LCD_PAD, middle - STRIP_HEIGHT // 2 - 6,
                                   x1 - SEGMENT_GAP - x0 + LCD_PAD * 2, STRIP_HEIGHT + 12)
        regions['loudness_hit'] = wx.Rect(x0, top, x1 - x0, bottom - top)
        for key in ('M', 'S', 'I'):
            rows.pop(key)
        regions['rows'] = rows
        regions['boxes'] = boxes
        regions['name_x'] = x1 - SEGMENT_GAP + CLIP_GAP + CLIP_WIDTH + NAME_GAP
        regions['readout_x'] = right - READOUT * 2
        regions['clips'] = [wx.Rect(x1 - SEGMENT_GAP + CLIP_GAP, rows[key].y, CLIP_WIDTH, BAR)
                            for key in ('L', 'R')]
        regions['segments'] = self.get_segments(rows['L'])
        regions['segment_dbs'] = [segment[1] for segment in regions['segments']]
        regions['segment_rects'] = {key: [(x, row.y, SEGMENT, row.height)
                                          for x, db, colour, half in regions['segments']]
                                    for key, row in rows.items()}
        xs = [segment[0] for segment in regions['segments']]
        regions['phase_segments'] = xs
        regions['phase_middle'] = len(xs) // 2

    def get_segments(self, row):
        pitch = SEGMENT + SEGMENT_GAP
        segments = []
        for index in range(row.width // pitch):
            x = row.x + index * pitch
            db = self.from_x(row, x + SEGMENT)
            colour = self.get_colour(self.from_x(row, x + SEGMENT / 2))
            half = mix(colour, RACK['lcd'], SEGMENT_HALF).GetAsString(wx.C2S_HTML_SYNTAX)
            segments.append((x, db, colour, half))
        return segments

    def to_x(self, row, db):
        ratio = (min(max(db, METER_FLOOR), 0.0) - METER_FLOOR) / -METER_FLOOR
        return row.x + row.width * ratio

    def from_x(self, row, x):
        ratio = (x - row.x) / max(1, row.width)
        return METER_FLOOR + -METER_FLOOR * min(max(ratio, 0.0), 1.0)

    def build_background(self, width, height):
        bitmap = wx.Bitmap(max(1, width), max(1, height))
        dc = wx.MemoryDC(bitmap)
        dc.SetBackground(wx.Brush(wx.Colour(RACK['bg'])))
        dc.Clear()
        gc = wx.GraphicsContext.Create(dc)
        regions = self.layout(width)
        self.geometry = self.get_geometry(regions)
        plate = regions['plate']
        draw_rails(gc, self.left_margin, 0, width - self.left_margin - self.right_margin, height,
                   EAR)
        face, accent = FACES['master']

        draw_faceplate(gc, plate.x, plate.y, plate.width, plate.height, face, EAR, accent)
        power, fold = regions['icon'], regions['fold']
        hover = getattr(self, 'hover_target', None)
        if hover == 'fold':
            fill_rect(gc, RACK['button_hover'], fold.x, fold.y, fold.width, fold.height, 3)
        draw_glyph(gc, 'right' if self.folded else 'down', fold.x + fold.width / 2,
                   fold.y + fold.height / 2, 10, RACK['text'] if hover == 'fold' else RACK['dim'])
        self.draw_icon(gc, power, RACK['dim'])
        self.draw_pin(gc, regions['pin'], accent)
        draw_title(gc, power.x + 22, plate.y, TITLE, '', RACK['dim'], plate.width // 2)
        for name, chip in regions['chips'].items():
            draw_chip(gc, chip, regions['chip_labels'][name], not self.parts[name],
                      hover == 'part:' + name)
        if 'screen' in regions:
            draw_lcd(gc, regions['screen'])
            for divider in regions['dividers']:
                fill_rect(gc, RACK['lcd_rim'], divider.x, divider.y, divider.width, 1)
        if 'level' in regions:
            self.draw_level_ground(gc, regions)
        if 'spectrum' in regions:
            self.draw_spectrum_ground(gc, regions)
        if 'oscilloscope' in regions:
            self.draw_wave_ground(gc, regions)
        if 'strip' in regions:
            self.draw_strip_ground(gc, regions)
        if 'scope' in regions:
            self.draw_scope_ground(gc, regions)
        if 'correlation' in regions:
            self.draw_phase_ground(gc, regions)
        del gc
        dc.SelectObject(wx.NullBitmap)
        self.lit = self.build_lit(bitmap, regions) if 'level' in regions else None
        return bitmap

    def get_geometry(self, regions):
        inners = {'spectrum': self.get_spectrum_inner, 'oscilloscope': self.get_wave_inner,
                  'spectrogram': self.get_spectrum_inner, 'scope': wx.Rect,
                  'strip': self.get_bars_inner}
        return {name: Box(*inner(regions[name]).Get()) for name, inner in inners.items()
                if name in regions}

    def build_lit(self, background, regions):
        # every segment lit over the ground; a frame copies the spans it needs
        body = regions['level']
        # the first paint comes before layout, on a 20x20 window
        if body.width <= 0 or body.height <= 0 or not wx.Rect(background.GetSize()).Contains(body):
            return None
        sources = []
        for index, phase in ((2, METER_BLUE), (3, METER_MID)):
            dc = wx.MemoryDC(background.GetSubBitmap(body))
            dc.SetDeviceOrigin(-body.x, -body.y)
            dc.SetPen(wx.TRANSPARENT_PEN)
            for key in ('L', 'R'):
                for segment, rect in zip(regions['segments'], regions['segment_rects'][key]):
                    dc.SetBrush(get_brush(segment[index]))
                    dc.DrawRectangle(*rect)
            dc.SetBrush(get_brush(phase))
            for key in ('correlation', 'balance'):
                bar = regions[key]
                for x in regions['phase_segments']:
                    dc.DrawRectangle(x, bar.y, SEGMENT, bar.height)
            sources.append(dc)
        return sources

    def draw_icon(self, gc, rect, accent):
        bottom = rect.y + rect.height - 2
        for index, height in enumerate((6, 11, 8)):
            fill_rect(gc, accent, rect.x + 2 + index * 4, bottom - height, 2, height, 1)

    def draw_pin(self, gc, rect, accent):
        draw_chip(gc, rect, 'PIN', self.pinned, getattr(self, 'hover_target', None) == 'pin')


    def draw_level_ground(self, gc, regions):
        rows = regions['rows']
        first, last = rows['L'], rows['R']
        scale_y = regions['scale_y']
        drawn = None
        for value in METER_SCALE:
            x = round(self.to_x(first, value))
            fill_rect(gc, RACK['lcd_axis'] if value == 0 else RACK['lcd_grid'], x, first.y - 2,
                      1, last.y + last.height + 2 - (first.y - 2))
            # left-align -48 so its minus clears the left rule
            first_label = value == METER_SCALE[-1]
            if drawn is None or drawn - x >= (26 if first_label else 18):
                draw_text(gc, str(value), x, scale_y + 1, 6.5, RACK['lcd_text'],
                          align='left' if first_label else 'center')
                drawn = x
        for key, row in rows.items():
            tone = LOUDNESS_COLOURS.get(key)
            for x, db, colour, half in regions['segments']:
                fill_rect(gc, mix(tone or colour, RACK['lcd'], SEGMENT_OFF), x, row.y, SEGMENT,
                          row.height)
            draw_text(gc, key, regions['name_x'] + NAME_WIDTH / 2, row.y - 3, 7.5,
                      tone or RACK['lcd_text'], bold=True, align='center')
        boxes = regions['boxes']
        # monospace labels end flush with the numbers
        gc.SetFont(get_mono(6.5), wx.Colour(RACK['faint']))
        labels = [(boxes['Lpk'].x + boxes['Lpk'].width + 1, scale_y + 1, 'PK'),
                  (boxes['Lrms'].x + boxes['Lrms'].width + 1, scale_y + 1, 'RMS')]
        labels += [(boxes[key].x + boxes[key].width * 2, boxes[key].y + 1, text)
                   for key, text in LOUDNESS_NAMES.items()]
        labels += [(box.x + box.width * 2, box.y + 1, PHASE_NAMES[key])
                   for key, box in regions['phase_boxes'].items()]
        for x, y, text in labels:
            # monospace ink ends 1 px inside the cell (measured)
            gc.DrawText(text, x - gc.GetTextExtent(text)[0] + 1, y)
        for clip in regions['clips']:
            fill_rect(gc, RACK['lcd_grid'], clip.x, clip.y, clip.width, clip.height)

    def draw_spectrum_ground(self, gc, regions):
        inner = self.get_spectrum_inner(regions['spectrum'])
        for freq in SPECTRUM_FREQS:
            x = round(self.freq_x(inner, freq))
            fill_rect(gc, RACK['lcd_grid'], x, inner.y, 1, inner.height)
        for db in SPECTRUM_DBS:
            y = round(self.db_y(inner, db))
            fill_rect(gc, RACK['lcd_axis'] if db == 0 else RACK['lcd_grid'], inner.x, y,
                      inner.width, 1)

    def get_wave_inner(self, rect):
        return wx.Rect(rect.x + LCD_PAD, rect.y + LCD_PAD, rect.width - LCD_PAD * 2,
                       rect.height - LCD_PAD * 2)

    def draw_wave_ground(self, gc, regions):
        inner = self.get_wave_inner(regions['oscilloscope'])
        for y in (inner.y + inner.height // 4, inner.y + inner.height * 3 // 4):
            fill_rect(gc, RACK['lcd_grid'], inner.x, y, inner.width, 1)
        fill_rect(gc, RACK['lcd_axis'], inner.x, inner.y + inner.height // 2, inner.width, 1)

    def draw_gram_labels(self, dc, inner):
        font = get_font(6.5)
        dc.SetFont(font)
        dc.SetTextForeground(wx.Colour(RACK['lcd_text']))
        for freq in GRAM_FREQS:
            y = round(self.gram_y(inner, freq))
            text = get_short_hz(freq)
            width, height = self.get_extent(dc, font, text)
            # the right edge would hide incoming sound
            dc.DrawText(text, inner.x + 4, y - height // 2)

    def gram_y(self, inner, freq):
        ratio = math.log(min(max(freq, 20.0), 20000.0) / 20.0) / math.log(1000.0)
        return inner.y + inner.height - 1 - (inner.height - 1) * ratio

    def draw_spectrum_labels(self, dc, inner):
        font = get_font(6.5)
        dc.SetFont(font)
        dc.SetTextForeground(wx.Colour(RACK['lcd_text']))
        bottom = inner.y + inner.height
        last = len(SPECTRUM_FREQS) - 1
        for index, freq in enumerate(SPECTRUM_FREQS):
            x = round(self.freq_x(inner, freq))
            text = get_short_hz(freq)
            width, height = self.get_extent(dc, font, text)
            left = x + 3 if index == 0 else x - width - 3 if index == last else x - width // 2
            dc.DrawText(text, left, bottom - height - 2)
        step = 2 if self.db_y(inner, -12) - self.db_y(inner, 0) < 16 else 1
        for db in SPECTRUM_DBS[:-1][::step]:
            y = round(self.db_y(inner, db))
            text = str(db)
            width, height = self.get_extent(dc, font, text)
            dc.DrawText(text, inner.x + inner.width - width - 4, y + 1 if db == 0 else y - height)

    def draw_strip_ground(self, gc, regions):
        gc.SetPen(wx.TRANSPARENT_PEN)
        gc.SetBrush(wx.Brush(mix(METER_BLUE, RACK['lcd'], SEGMENT_OFF)))
        bars = self.get_bars_inner(regions['strip'])
        for rect in self.get_bar_rects(bars, [0.0] * (len(self.get_bar_bins()) - 1)):
            gc.DrawRectangle(rect[0], rect[1], rect[2], rect[3])

    def get_scope_radius(self, scope):
        return min(scope.width, scope.height) / 2 - 5

    def draw_scope_ground(self, gc, regions):
        divider = regions['scope_divider']
        fill_rect(gc, RACK['lcd_grid'], divider.x, divider.y, divider.width, divider.height)
        scope = regions['scope']
        cx, cy = scope.x + scope.width / 2, scope.y + scope.height / 2
        radius = self.get_scope_radius(scope)
        gc.SetPen(wx.Pen(wx.Colour(RACK['lcd_grid']), 1))
        gc.StrokeLine(cx, cy - radius, cx, cy + radius)
        gc.StrokeLine(cx - radius * 0.7, cy - radius * 0.7, cx + radius * 0.7, cy + radius * 0.7)
        gc.StrokeLine(cx + radius * 0.7, cy - radius * 0.7, cx - radius * 0.7, cy + radius * 0.7)
        draw_text(gc, 'L', cx - radius * 0.7 - 2, cy - radius * 0.7 - 4, 7, RACK['lcd_text'],
                  align='right')
        draw_text(gc, 'R', cx + radius * 0.7 + 2, cy - radius * 0.7 - 4, 7, RACK['lcd_text'])

    def draw_phase_ground(self, gc, regions):
        xs = regions['phase_segments']
        off = mix(METER_BLUE, RACK['lcd'], SEGMENT_OFF)
        middle = xs[regions['phase_middle']]
        for key in ('correlation', 'balance'):
            bar = regions[key]
            for x in xs:
                fill_rect(gc, off, x, bar.y, SEGMENT, bar.height)
            fill_rect(gc, RACK['lcd_axis'], middle, bar.y - 2, SEGMENT, 2)
            fill_rect(gc, RACK['lcd_axis'], middle, bar.y + bar.height, SEGMENT, 2)

    def get_bars_inner(self, rect):
        return wx.Rect(rect.x + LCD_PAD, rect.y + 6, rect.width - LCD_PAD * 2, rect.height - 12)

    def get_bar_scale(self):
        width = self.geometry['strip'].width
        return max(1, round(width / (BAR_SET * BAR_PITCH)))

    def get_bar_bins(self):
        scale = self.get_bar_scale()
        if self.bar_bins is not None and self.bar_bins[0] == scale:
            return self.bar_bins[1]
        limit = BAR_POINTS // 2 - 1
        bins = list(BAR_LOW_PAD) + [freq for freq in BAR_NOTES
                                    if 8 < freq < limit + len(BAR_LOW_PAD) + 1] + [limit]
        for index in range(len(bins) - 1, 0, -1):
            step = (bins[index] - bins[index - 1]) / scale
            for part in range(scale - 1, 0, -1):
                bins.insert(index, bins[index - 1] + step * part)
        self.bar_bins = (scale, bins)
        return bins

    def get_bar_rects(self, rect, levels, floor=1):
        xs, halves, middle = self.get_bar_spans(rect, levels, floor)
        return [(int(x), int(middle - half), BAR_WIDTH, int(half * 2)) for x, half in zip(xs, halves)]

    def get_bar_spans(self, rect, levels, floor):
        count = max(2, rect.width // BAR_PITCH + 1)
        levels = numpy.asarray(levels, dtype='float64')
        source = len(levels)
        if source < 2:
            levels = numpy.resize(levels, count)
        elif count >= source:
            levels = numpy.interp(numpy.linspace(0, source - 1, count), numpy.arange(source),
                                  levels)
        else:
            edges = numpy.linspace(0, source, count + 1).astype(int)
            edges[1:] = numpy.maximum(edges[1:], edges[:-1] + 1)
            levels = numpy.maximum.reduceat(levels, numpy.minimum(edges[:-1], source - 1))
        offset = (rect.width - BAR_PITCH * (count - 1)) // 2
        # halves round together so bar ends stay even
        middle = rect.y + rect.height // 2
        halves = numpy.maximum(floor, numpy.round(levels * rect.height * BAR_HEIGHT / 2)).astype(int)
        return rect.x + BAR_PITCH * numpy.arange(count) + offset, halves, middle

    def get_spectrum_inner(self, rect):
        return wx.Rect(rect.x + LCD_PAD, rect.y + LCD_PAD, rect.width - LCD_PAD * 2,
                       rect.height - LCD_PAD * 2)

    def freq_x(self, inner, freq):
        return inner.x + inner.width * math.log(min(max(freq, 20.0), 20000.0) / 20.0) / \
            math.log(1000.0)

    def db_y(self, inner, db):
        ratio = (min(max(db, SPECTRUM_FLOOR), 0.0) - SPECTRUM_FLOOR) / -SPECTRUM_FLOOR
        return inner.y + inner.height * (1 - ratio)

    def db_ys(self, inner, dbs):
        ratio = (numpy.clip(dbs, SPECTRUM_FLOOR, 0.0) - SPECTRUM_FLOOR) / -SPECTRUM_FLOOR
        return inner.y + inner.height * (1 - ratio)

    def on_paint(self, event):
        # a fresh buffer per frame costs milliseconds
        width, height = self.GetClientSize()
        if self.buffer is None or self.buffer.GetSize() != wx.Size(width, height):
            self.buffer = wx.Bitmap(max(1, width), max(1, height))
        dc = wx.BufferedPaintDC(self, self.buffer)
        with self.lock:
            self.paint(dc, width, height)

    def paint(self, dc, width, height):
        key = (width, height, self.folded, self.pinned, self.flowing, self.left_margin,
               self.right_margin,
               tuple(self.parts.values()), getattr(self, 'hover_target', None),
               CONTROL_ACCENT['rack'])
        if self.background is None or self.background_key != key:
            self.background = self.build_background(width, height)
            self.background_key = key
        dc.DrawBitmap(self.background, 0, 0)
        if not self.regions or 'level' in self.regions and self.lit is None:
            return
        if not self.is_running():
            if 'spectrum' in self.regions:
                self.draw_spectrum_labels(dc, self.get_spectrum_inner(self.regions['spectrum']))
            self.draw_status(dc)
            return
        self.draw_levels(dc)
        self.draw_spectrum(dc)
        self.draw_scope(dc)
        self.draw_wave(dc)
        self.draw_gram(dc)
        self.draw_status(dc)

    def draw_wave(self, dc):
        if 'oscilloscope' not in self.regions:
            return
        inner = self.get_wave_inner(self.regions['oscilloscope'])
        if self.wave is None or inner.width <= 3:
            return
        self.fit_wave(inner.width)
        # GDI lines per column cost 3 ms; paint columns into one image
        height, width = inner.height, inner.width
        image = self.wave_image
        pushed = self.wave_pushed
        if image is None or image.shape[:2] != (height, width) or \
                self.wave_source is not self.wave or pushed >= width:
            image = self.wave_image = numpy.zeros((height, width, 4), dtype='uint8')
            self.paint_wave(image, self.wave)
            self.wave_source = self.wave
            self.wave_bitmap = wx.Bitmap.FromBufferRGBA(width, height, image)
        elif pushed:
            image[:, :-pushed] = image[:, pushed:]
            image[:, -pushed:] = 0
            self.paint_wave(image[:, -pushed:], self.wave[:, -pushed:])
            self.wave_bitmap.CopyFromBuffer(image, wx.BitmapBufferFormat_RGBA)
        self.wave_pushed = 0
        dc.DrawBitmap(self.wave_bitmap, inner.x, inner.y)

    def paint_wave(self, image, wave):
        height = image.shape[0]
        middle = height / 2
        high, low, rms = wave
        rows = numpy.arange(height)[:, None]
        top = numpy.floor(middle - numpy.clip(high, -1, 1) * (middle - 1))[None, :]
        bottom = numpy.ceil(middle - numpy.clip(low, -1, 1) * (middle - 1))[None, :]
        reach = numpy.clip(rms, 0, 1) * (middle - 1)
        inside = (rows >= numpy.floor(middle - reach)[None, :]) & (rows <= numpy.ceil(middle + reach)[None, :])
        peak, body = self.get_wave_colour()
        image[(rows >= top) & (rows <= bottom)] = peak
        image[inside & (reach[None, :] > 0.5)] = body

    def get_wave_colour(self):
        if getattr(self, 'wave_colour', None) is None:
            self.wave_colour = (list(mix(TRACE_BLUE, RACK['lcd'], 0.45).Get()[:3]) + [255],
                                list(wx.Colour(TRACE_BLUE).Get()[:3]) + [255])
        return self.wave_colour

    def fit_gram(self, height, width):
        # also called while drawing: skipping a frame at a new size flickered
        if self.gram is not None and self.gram.shape[:2] == (height, width):
            return
        colours = self.get_gram_colours()
        fresh = numpy.empty((height, width, 3), dtype='uint8')
        fresh[:] = colours[0]
        old = self.gram
        if old is not None and old.size:
            rows = numpy.minimum((numpy.arange(height) * old.shape[0]) // height, old.shape[0] - 1)
            keep = min(width, old.shape[1])
            fresh[:, width - keep:] = old[rows][:, old.shape[1] - keep:]
            self.gram_dark = 0 if keep else width
        else:
            self.gram_dark = width
        self.gram = fresh

    def fit_wave(self, width):
        if self.wave is not None and self.wave.shape[1] == width:
            return
        fresh = numpy.zeros((3, width))
        if self.wave is not None:
            keep = min(width, self.wave.shape[1])
            fresh[:, width - keep:] = self.wave[:, self.wave.shape[1] - keep:]
            self.wave_dark = 0
        else:
            self.wave_dark = width
        self.wave = fresh

    def draw_gram(self, dc):
        if 'spectrogram' not in self.regions:
            return
        inner = self.get_spectrum_inner(self.regions['spectrogram'])
        if self.gram is not None and inner.width > 3 and inner.height > 3:
            self.fit_gram(inner.height, inner.width)
            height, width = self.gram.shape[:2]
            if self.gram_bitmap is None or self.gram_source is not self.gram:
                self.gram_bitmap = wx.Bitmap.FromBuffer(width, height, self.gram)
                self.gram_source = self.gram
            elif self.gram_drawn != self.gram_serial:
                self.gram_bitmap.CopyFromBuffer(self.gram, wx.BitmapBufferFormat_RGB)
            self.gram_drawn = self.gram_serial
            dc.DrawBitmap(self.gram_bitmap, inner.x, inner.y)
        self.draw_gram_labels(dc, inner)

    def get_extent(self, dc, font, text):
        key = (id(font), text)
        extent = self.extents.get(key)
        if extent is None:
            if len(self.extents) > 4096:
                self.extents.clear()
            extent = self.extents[key] = dc.GetTextExtent(text)
        return extent

    def draw_status(self, dc):
        plate = self.regions['plate']
        right = self.regions['pin'].x - 8
        if self.capture.error:
            text = self.capture.error
        else:
            text = self.capture.device
        font = get_font(8)
        dc.SetFont(font)
        dc.SetTextForeground(wx.Colour(RACK['warn'] if self.capture.error else RACK['dim']))
        limit = right - self.regions['chips_end'] - 16
        if limit < 40:
            return
        while text and self.get_extent(dc, font, text)[0] > limit:
            text = text[:-2] + '…'
        top = plate.y + (FOLDED - self.get_extent(dc, font, text or 'X')[1]) // 2
        dc.DrawText(text, right - self.get_extent(dc, font, text)[0], top)

    def get_colour(self, db):
        if db >= -3:
            return METER_HIGH
        if db >= -9:
            return METER_MID
        return METER_BLUE

    def draw_levels(self, dc):
        regions = self.regions
        if 'level' not in regions:
            return
        rows = regions['rows']
        momentary, short, integrated = self.loudness or (LOUDNESS_FLOOR,) * 3
        dbs = regions['segment_dbs']
        holds = []
        for channel, key in enumerate(('L', 'R')):
            row = rows[key]
            rms, peak, hold = self.rms[channel], self.peak[channel], self.hold[channel]
            rects = regions['segment_rects'][key]
            lit = bisect.bisect_right(dbs, rms)
            dim = max(lit, bisect.bisect_right(dbs, peak))
            for source, start, end in ((self.lit[0], 0, lit), (self.lit[1], lit, dim)):
                if end > start:
                    x = rects[start][0]
                    width = rects[end - 1][0] + SEGMENT - x
                    dc.Blit(x, row.y, width, row.height, source, x, row.y)
            if hold > METER_FLOOR:
                holds.append((round(self.to_x(row, hold)) - 1, row.y - 2, 2, row.height + 4))
        dc.SetPen(wx.TRANSPARENT_PEN)
        if holds:
            dc.DrawRectangleList(holds, pens=wx.TRANSPARENT_PEN, brushes=get_brush('#f2f4f6'))
        for channel, clip in enumerate(regions['clips']):
            if self.clips[channel]:
                dc.SetBrush(get_brush(CLIP))
                dc.DrawRectangle(clip)

        values = {'Lpk': (self.hold[0], FLOOR), 'Rpk': (self.hold[1], FLOOR),
                  'Lrms': (self.rms[0], FLOOR), 'Rrms': (self.rms[1], FLOOR),
                  'M': (momentary, LOUDNESS_FLOOR), 'S': (short, LOUDNESS_FLOOR),
                  'I': (integrated, LOUDNESS_FLOOR)}
        font = get_mono(7.5)
        dc.SetFont(font)
        for key, box in regions['boxes'].items():
            value, floor = values[key]
            text = '--' if value <= floor else '%.1f' % value
            if key.endswith('pk'):
                colour = CLIP if value > -0.1 else RACK['text']
            elif key.endswith('rms'):
                colour = RACK['dim']
            else:
                colour = LOUDNESS_COLOURS[key]
            dc.SetTextForeground(wx.Colour(colour))
            width, height = self.get_extent(dc, font, text)
            dc.DrawText(text, box.x + box.width - width, box.y + (box.height - height) // 2)

    def format_db(self, value):
        return '-inf' if value <= FLOOR else '%.1f' % value

    def draw_spectrum(self, dc):
        self.draw_bars(dc)
        if 'spectrum' not in self.regions:
            return
        # skip when silent, or a line stays on the floor
        silent = (self.spectrum is not None and self.spectrum[1].max() <= SPECTRUM_FLOOR and
                  (self.spectrum_hold is None or
                   self.spectrum_hold[0].max() <= SPECTRUM_FLOOR))
        if self.spectrum is None or silent:
            self.draw_spectrum_labels(dc, self.get_spectrum_inner(self.regions['spectrum']))
            return
        rect = self.regions['spectrum']
        inner = self.get_spectrum_inner(rect)
        xs, values = self.spectrum
        ys = self.db_ys(inner, values)
        bottom = inner.y + inner.height
        gc = wx.GraphicsContext.Create(dc)
        if gc is None:
            return
        gc.Clip(inner.x, inner.y, inner.width, inner.height)
        points = list(zip(xs.tolist(), ys.tolist()))
        tone = wx.Colour(TRACE_BLUE)
        top = float(ys.min()) if len(ys) else inner.y
        gc.SetPen(wx.TRANSPARENT_PEN)
        gc.SetBrush(gc.CreateLinearGradientBrush(
            0, top, 0, bottom, wx.Colour(tone.Red(), tone.Green(), tone.Blue(), 150),
            wx.Colour(tone.Red(), tone.Green(), tone.Blue(), 12)))
        gc.DrawLines([(points[0][0], bottom)] + points + [(points[-1][0], bottom)])
        gc.SetPen(gc.CreatePen(wx.GraphicsPenInfo(wx.Colour(TRACE_BLUE)).Width(1.4).Join(wx.JOIN_ROUND)))
        gc.SetBrush(wx.TRANSPARENT_BRUSH)
        gc.StrokeLines(points)
        hold = self.spectrum_hold[0] if self.spectrum_hold is not None else None
        if hold is not None and len(hold) == len(xs):
            gc.SetPen(gc.CreatePen(wx.GraphicsPenInfo(wx.Colour(200, 204, 210, 110)).Width(1)))
            gc.StrokeLines(list(zip(xs.tolist(), self.db_ys(inner, hold).tolist())))
        gc.ResetClip()
        del gc
        self.draw_spectrum_labels(dc, inner)
        self.draw_hover(dc, inner, xs, values)

    def draw_hover(self, dc, inner, xs, values):
        if self.hover is None or not inner.Contains(wx.Point(self.hover, inner.y + 1)):
            return
        x = self.hover
        freq = 20.0 * 1000.0 ** ((x - inner.x) / max(1, inner.width))
        db = float(numpy.interp(x, xs, values))
        note = NOTE_NAMES[round(12 * math.log2(freq / 440.0) + 69) % 12]
        octave = (round(12 * math.log2(freq / 440.0) + 69)) // 12 - 1
        hz = '%.0f Hz' % freq if freq < 1000 else '%.2f kHz' % (freq / 1000)
        text = '%s  %s%d  %.1f dB' % (hz, note, octave, db)
        dc.SetPen(wx.Pen(wx.Colour(RACK['lcd_axis']), 1))
        dc.DrawLine(x, inner.y, x, inner.y + inner.height)
        dc.SetFont(get_mono(7.5))
        width, height = dc.GetTextExtent(text)
        box = wx.Rect(x + 6, inner.y + 4, width + 12, height + 6)
        if box.x + box.width > inner.x + inner.width:
            box.x = x - 6 - box.width
        dc.SetPen(wx.Pen(wx.Colour(RACK['lcd_rim']), 1))
        dc.SetBrush(get_brush(RACK['band']))
        dc.DrawRectangle(box)
        dc.SetTextForeground(wx.Colour(RACK['text']))
        dc.DrawText(text, box.x + 6, box.y + 3)

    def draw_scope(self, dc):
        regions = self.regions
        if 'scope' in regions and self.scope is not None:
            scope = regions['scope']
            if self.scope_source is not self.scope:
                height, width = self.scope.shape[:2]
                self.scope_bitmap = wx.Bitmap.FromBufferRGBA(width, height, self.scope)
                self.scope_source = self.scope
            dc.DrawBitmap(self.scope_bitmap, scope.x, scope.y)
        if 'correlation' not in regions:
            return
        dc.SetPen(wx.TRANSPARENT_PEN)
        dc.SetFont(get_mono(7.5))
        for key, ratio, value, tone in (
                ('correlation', (self.correlation + 1) / 2,
                 '%+.2f' % self.correlation if abs(self.correlation) >= 0.005 else '0.00',
                 METER_BLUE if self.correlation >= 0 else METER_MID),
                ('balance', 0.5 + max(-1.0, min(1.0, self.balance / BALANCE_RANGE)) / 2,
                 '%+.1f' % -self.balance if abs(self.balance) >= 0.05 else '0.0', METER_BLUE)):
            bar = regions[key]
            xs = regions['phase_segments']
            centre = regions['phase_middle']
            reach = round((ratio - 0.5) * 2 * centre)
            end = min(max(centre + reach, 0), len(xs) - 1)
            low, high = min(centre, end), max(centre, end)
            source = self.lit[0] if tone == METER_BLUE else self.lit[1]
            dc.Blit(xs[low], bar.y, xs[high] + SEGMENT - xs[low], bar.height, source, xs[low], bar.y)
            bright = mix(tone, '#ffffff', 0.45).GetAsString(wx.C2S_HTML_SYNTAX)
            dc.SetBrush(get_brush(bright))
            dc.DrawRectangle(xs[end], bar.y - 1, SEGMENT, bar.height + 2)
            box = regions['phase_boxes'][key]
            dc.SetTextForeground(wx.Colour(RACK['text']))
            width, height = dc.GetTextExtent(value)
            dc.DrawText(value, box.x + box.width - width, box.y + (box.height - height) // 2)

    def tick(self):
        # a queued call can arrive after close; a destroyed window is falsy
        if not self:
            return
        if self.pacer is not None:
            self.pacer.pending = False
        self.wanted = (self.is_running() and bool(self.regions) and self.IsShownOnScreen() and
                       not self.GetTopLevelParent().IsIconized() and
                       self.GetPosition().y + self.GetSize().height > 0)
        if not self.wanted:
            return
        with self.lock:
            dirty, self.dirty = self.dirty, False
        if not dirty:
            return
        plate = self.regions['plate']
        self.RefreshRect(wx.Rect(plate.x, plate.y + FOLDED, plate.width,
                                 self.GetClientSize().height - FOLDED), False)

    def analyze(self):
        # runs on the pacer thread under the lock; the frame is painted by tick
        now = time.perf_counter()
        elapsed = min(0.2, now - self.last)
        self.last = now
        peaks, rms, clips, recent = self.capture.take(FFT_SIZE)
        if max(peaks) == 0.0 and self.drawn_quiet and clips == self.clips:
            return
        self.clips = clips
        for channel in (0, 1):
            value = to_db(peaks[channel], FLOOR)
            self.peak[channel] = max(value, self.peak[channel] - PEAK_FALL * elapsed)
            if value >= self.hold[channel]:
                self.hold[channel] = value
                self.held_at[channel] = now
            elif now - self.held_at[channel] > HOLD_TIME:
                self.hold[channel] = max(FLOOR, self.hold[channel] - HOLD_FALL * elapsed)
            self.rms[channel] = to_db(rms[channel], FLOOR)
        if now - self.loudness_at > LOUDNESS_EVERY or self.loudness is None:
            self.loudness_at = now
            self.loudness = self.capture.take_loudness()
        self.frame_power = None
        self.update_spectrum(recent, elapsed)
        self.update_scope(recent[-SCOPE_SAMPLES:])
        self.update_wave(recent, elapsed)
        self.update_gram(recent)
        quiet = (max(peaks) == 0.0 and max(self.peak) <= FLOOR and max(self.hold) <= FLOOR and
                 (self.spectrum is None or self.spectrum[1].max() <= SPECTRUM_FLOOR) and
                 # wait for the peak line too, or it freezes above the floor
                 (self.spectrum_hold is None or self.spectrum_hold[0].max() <= SPECTRUM_FLOOR) and
                 (self.bars is None or self.bars.max() < 1e-3) and
                 abs(self.correlation) < 0.005 and abs(self.balance) < 0.05 and
                 (self.gram is None or self.gram_dark >= self.gram.shape[1]) and
                 (self.wave is None or self.wave_dark >= self.wave.shape[1]))
        if quiet and self.drawn_quiet:
            return
        self.drawn_quiet = quiet
        self.dirty = True

    def draw_bars(self, dc):
        if self.bars is None or 'strip' not in self.regions:
            return
        rect = self.get_bars_inner(self.regions['strip'])
        xs, halves, middle = self.get_bar_spans(rect, numpy.minimum(self.bars, 1.0 / BAR_HEIGHT), 0)
        inside = (xs >= rect.x) & (xs < rect.x + rect.width)
        xs, halves = xs[inside] - rect.x, halves[inside]
        rows = numpy.arange(rect.y, rect.y + rect.height)[:, None]
        # zero bars stay transparent so the floor dots show
        lit = (rows >= middle - halves[None, :]) & (rows < middle + halves[None, :])
        columns = numpy.zeros((rect.height, len(xs), 4), dtype='uint8')
        columns[lit] = self.get_bar_colour()
        image = numpy.zeros((rect.height, rect.width, 4), dtype='uint8')
        image[:, xs] = columns
        if self.bars_bitmap is None or self.bars_bitmap.GetSize() != rect.GetSize():
            self.bars_bitmap = wx.Bitmap.FromBufferRGBA(rect.width, rect.height, image)
        else:
            self.bars_bitmap.CopyFromBuffer(image, wx.BitmapBufferFormat_RGBA)
        dc.DrawBitmap(self.bars_bitmap, rect.x, rect.y)

    def get_bar_colour(self):
        return list(wx.Colour(BAR_COLOUR).Get()[:3]) + [255]

    def update_bars(self, recent, elapsed):
        scale = self.get_bar_scale()
        bins = self.get_bar_bins()
        left = recent[-BAR_FRAME:, 0].astype('float64')
        raw = numpy.abs(numpy.fft.fft(left, BAR_POINTS))[1:BAR_POINTS // 2]
        self.follow_autogain(raw, elapsed)
        amplify = (self.autogain * (1.0 / 0.4) * 2 * (RATE / 44100.0) * 1.25 *
                   math.sqrt(min(scale, 3)))
        spectrum = raw * 32768.0 * amplify / BAR_POINTS / 8192
        reach, logs, roots, powers = self.get_bar_weights(bins, len(spectrum))
        levels = spectrum[reach].max(axis=1) * logs * roots
        self.bars = (levels ** powers) * 1.5

    def get_bar_weights(self, bins, size):
        # windows overlap, so short ones repeat their last bin
        if self.bar_weights is not None and self.bar_weights[0] is bins:
            return self.bar_weights[1]
        lows, highs, logs, roots, powers = [], [], [], [], []
        for index, value in enumerate(bins[:-1]):
            low = max(0, int(value) - BAR_REACH)
            lows.append(low)
            highs.append(min(size, max(int(bins[index + 1]) + 1, int(value) + BAR_REACH + 1)))
            logs.append(math.log(1 + value, 2))
            roots.append(value ** 0.25)
            powers.append(1.4 * ((2 + index) / (1 + index)))
        lows, highs = numpy.array(lows), numpy.array(highs)
        reach = lows[:, None] + numpy.arange((highs - lows).max())[None, :]
        reach = numpy.minimum(reach, highs[:, None] - 1)
        weights = (reach, numpy.array(logs), numpy.array(roots), numpy.array(powers))
        self.bar_weights = (bins, weights)
        return weights

    def follow_autogain(self, raw, elapsed):
        # Parseval: zero padding adds no energy
        energy = 2.0 * float((raw ** 2 * AUTOGAIN_WEIGHTS).sum()) / BAR_POINTS / BAR_FRAME
        rms = math.sqrt(energy) * 3
        if rms < 1e-4:
            return
        low, high = AUTOGAIN_RANGE
        target = min(high, max(low, 0.14 / rms))
        self.autogain += (target - self.autogain) * min(1.0, elapsed / AUTOGAIN_FOLLOW)

    def update_spectrum(self, recent, elapsed):
        if 'strip' in self.geometry:
            self.update_bars(recent, elapsed)
        if 'spectrum' not in self.geometry:
            return
        inner = self.geometry['spectrum']
        if inner.width < 8:
            return
        power = self.get_frame_power(recent)
        if self.spectrum_bins is None or self.spectrum_bins[0] != (inner.x, inner.width):
            freqs = numpy.fft.rfftfreq(FFT_SIZE, 1.0 / RATE)
            columns = max(32, inner.width // 2)
            edges = 20.0 * numpy.power(1000.0, numpy.linspace(0, 1, columns + 1))
            centres = numpy.sqrt(edges[:-1] * edges[1:])
            starts = numpy.minimum(numpy.searchsorted(freqs, edges[:-1]), len(freqs) - 1)
            stops = numpy.maximum(numpy.searchsorted(freqs, edges[1:]), starts + 1)
            counts = numpy.maximum(numpy.diff(numpy.append(starts, len(freqs))), 1)
            # low bands are narrower than a bin; interpolate at the band centre
            narrow = (stops - starts) <= 1
            tilt = SPECTRUM_TILT * numpy.log2(centres / 1000.0)
            xs = numpy.array([self.freq_x(inner, freq) for freq in centres])
            self.spectrum_bins = ((inner.x, inner.width),
                                  (freqs, columns, centres, starts, counts, narrow, tilt, xs))
        freqs, columns, centres, starts, counts, narrow, tilt, xs = self.spectrum_bins[1]
        values = numpy.add.reduceat(power, starts) / counts
        if narrow.any():
            values[narrow] = numpy.interp(centres[narrow], freqs, power)
        values = 10 * numpy.log10(numpy.maximum(values, 1e-12))
        values += tilt
        previous = self.spectrum
        if previous is not None and len(previous[1]) == columns:
            values = previous[1] + (values - previous[1]) * SPECTRUM_SMOOTH
            hold, held = self.spectrum_hold
            now = time.perf_counter()
            rising = values > hold
            held = numpy.where(rising, now, held)
            falling = (~rising) & (now - held > PEAK_LINE_HOLD)
            hold = numpy.where(rising, values, hold)
            hold = numpy.where(falling, numpy.maximum(values, hold - PEAK_LINE_FALL * elapsed),
                               hold)
            self.spectrum_hold = (hold, held)
        else:
            self.spectrum_hold = (values.copy(), numpy.full(columns, time.perf_counter()))
        self.spectrum = (xs, values)

    def get_frame_power(self, recent):
        if self.frame_power is None:
            mono = recent.mean(axis=1) * self.window
            self.frame_power = (numpy.abs(numpy.fft.rfft(mono)) * (4.0 / FFT_SIZE)) ** 2
        return self.frame_power

    def update_wave(self, recent, elapsed):
        if 'oscilloscope' not in self.geometry:
            return
        width = self.geometry['oscilloscope'].width
        if width < 4:
            return
        self.fit_wave(width)
        count = min(len(recent), max(1, int(round(elapsed * RATE))))
        mono = recent[-count:].mean(axis=1)
        column = (float(mono.max()), float(mono.min()), float(numpy.sqrt((mono ** 2).mean())))
        self.wave[:, :-1] = self.wave[:, 1:]
        self.wave[:, -1] = column
        self.wave_pushed += 1
        self.wave_dark = self.wave_dark + 1 if max(abs(column[0]), abs(column[1])) < 1e-4 else 0

    def get_gram_colours(self):
        return self.gram_colours

    def update_gram(self, recent):
        if 'spectrogram' not in self.geometry:
            return
        inner = self.geometry['spectrogram']
        height, width = inner.height, inner.width
        if height < 4 or width < 4:
            return
        colours = self.get_gram_colours()
        self.fit_gram(height, width)
        if self.gram_rows is None or self.gram_rows[0] != height:
            freqs = numpy.fft.rfftfreq(FFT_SIZE, 1.0 / RATE)
            edges = 20.0 * numpy.power(1000.0, numpy.linspace(0, 1, height + 1))[::-1]
            highs, lows = edges[:-1], edges[1:]
            centres = numpy.sqrt(highs * lows)
            starts = numpy.minimum(numpy.searchsorted(freqs, lows), len(freqs) - 1)
            stops = numpy.maximum(numpy.searchsorted(freqs, highs), starts + 1)
            tilt = SPECTRUM_TILT * numpy.log2(centres / 1000.0)
            self.gram_rows = (height, freqs, centres, starts, stops, tilt)
        _, freqs, centres, starts, stops, tilt = self.gram_rows
        power = self.get_frame_power(recent)
        cumulative = numpy.concatenate(([0.0], numpy.cumsum(power)))
        values = (cumulative[stops] - cumulative[starts]) / (stops - starts)
        narrow = (stops - starts) <= 1
        if narrow.any():
            values[narrow] = numpy.interp(centres[narrow], freqs, power)
        db = 10 * numpy.log10(numpy.maximum(values, 1e-12)) + tilt
        level = numpy.clip((db - GRAM_LOW) / (GRAM_HIGH - GRAM_LOW), 0.0, 1.0)
        index = (level * 255).astype(int)
        self.gram[:, :-1] = self.gram[:, 1:]
        self.gram[:, -1] = colours[index]
        self.gram_serial += 1
        self.gram_dark = self.gram_dark + 1 if index.max() == 0 else 0

    def update_scope(self, block):
        left, right = block[:, 0], block[:, 1]
        if 'scope' in self.geometry:
            self.update_glow(self.geometry['scope'], left, right)
        # settle at centre in silence, or it looks like sound
        denominator = float(numpy.sqrt((left ** 2).sum() * (right ** 2).sum()))
        value = float((left * right).sum()) / denominator if denominator > 1e-9 else 0.0
        self.correlation += (value - self.correlation) * 0.25
        value = self.rms[0] - self.rms[1] if min(self.rms) > FLOOR else 0.0
        self.balance += (value - self.balance) * 0.15

    def update_glow(self, scope, left, right):
        energy = float(numpy.sqrt((left ** 2 + right ** 2).mean()))
        target = min(8.0, 0.35 / max(energy, 1e-4))
        self.scope_gain += (target - self.scope_gain) * 0.15
        radius = self.get_scope_radius(scope)
        width, height = scope.width, scope.height
        side = (right - left) * 0.7071 * radius * self.scope_gain
        mid = (right + left) * 0.7071 * radius * self.scope_gain
        # per-dot drawing costs 3 ms; accumulate into a brightness map
        if self.scope_glow is None or self.scope_glow.shape != (height, width):
            self.scope_glow = numpy.zeros((height, width), dtype='float32')
        glow = self.scope_glow
        glow *= SCOPE_PERSIST
        if energy >= 1e-5:
            xs = numpy.clip(width / 2 + side, 0, width - 1).astype(int)
            ys = numpy.clip(height / 2 - mid, 0, height - 1).astype(int)
            hits = numpy.bincount(ys * width + xs, minlength=width * height)
            glow += hits.reshape(height, width).astype('float32') * SCOPE_DOT
            numpy.minimum(glow, 1.0, out=glow)
        if glow.max() < 0.02:
            self.scope = None
        else:
            self.scope = self.paint_glow(glow)

    def paint_glow(self, glow):
        # zero cells stay transparent so the grid shows through
        level = glow[..., None]
        rgb = (GLOW_BASE + (GLOW_DOT - GLOW_BASE) * level).astype('uint8')
        alpha = (numpy.minimum(1.0, glow * 4) * 255).astype('uint8')
        return numpy.dstack([rgb, alpha[..., None]])

    def hit(self, point):
        if not self.regions:
            return None
        if wx.Rect(self.regions['fold']).Inflate(3, 3).Contains(point):
            return 'fold'
        if wx.Rect(self.regions['pin']).Inflate(3, 3).Contains(point):
            return 'pin'
        for name, chip in self.regions.get('chips', {}).items():
            if chip.Contains(point):
                return 'part:' + name
        for clip in self.regions['clips']:
            if wx.Rect(clip).Inflate(3, 3).Contains(point):
                return 'clip'
        box = self.regions.get('boxes', {}).get('I')
        if box is not None and box.Contains(point):
            return 'integrated'
        return None

    def on_down(self, event):
        target = self.hit(event.GetPosition())
        if target and target.startswith('part:'):
            name = target[5:]
            self.set_part_hidden(name, not self.parts[name])
        elif target == 'fold':
            self.set_folded(not self.folded)
        elif target == 'pin':
            self.set_pinned(not self.pinned)
        elif target == 'clip':
            self.capture.reset_clips()
            with self.lock:
                self.clips = [False, False]
                self.hold = [FLOOR, FLOOR]
            self.Refresh(False)
        elif target == 'integrated':
            self.capture.reset_integrated()
            with self.lock:
                self.loudness = None

    def on_wheel(self, event):
        if (not self.pinned or self.flowing) and self.on_wheel_rack is not None:
            self.on_wheel_rack(event)

    on_wheel_rack = None

    def on_leave(self, event):
        self.set_hover(None)
        self.set_hover_target(None)
        event.Skip()

    def set_hover_target(self, target):
        if target in ('clip', 'integrated'):
            target = None
        if target == getattr(self, 'hover_target', None):
            return
        self.hover_target = target
        plate = self.regions.get('plate')
        if plate is not None:
            self.RefreshRect(wx.Rect(plate.x, plate.y, plate.width, FOLDED), False)

    def set_hover(self, x):
        if x == self.hover:
            return
        self.hover = x
        if 'spectrum' not in self.regions:
            return
        # while analyzing, the next frame draws it; painting per mouse move doubles the cost
        if self.wanted:
            with self.lock:
                self.dirty = True
        else:
            self.RefreshRect(self.regions['spectrum'], False)

    def on_motion(self, event):
        point = event.GetPosition()
        spectrum = self.regions.get('spectrum')
        inside = (spectrum is not None and self.is_running() and
                  self.get_spectrum_inner(spectrum).Contains(point))
        self.set_hover(point.x if inside else None)
        target = self.hit(point)
        self.set_hover_target(target)
        self.SetCursor(wx.Cursor(wx.CURSOR_HAND if target else wx.CURSOR_ARROW))
        tip = {'clip': 'Click to reset',
               'integrated': 'Integrated loudness. Click to start over',
               'fold': 'Unfold to analyze' if self.folded else 'Fold to stop analyzing',
               'part:level': 'Show or hide the level meter, vectorscope, spectrum bars, correlation and balance',
               'part:spectrum': 'Show or hide the spectrum',
               'part:oscilloscope': 'Show or hide the oscilloscope (same time axis as the spectrogram)',
               'part:spectrogram': 'Show or hide the spectrogram',
                              'pin': 'Scroll with the rack' if self.pinned else 'Pin to the top'}.get(target, '')
        if tip != (self.GetToolTipText() or ''):
            self.SetToolTip(tip or None)
