# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com

랙 맨 위에 고정된 출력 계기판. 레벨미터(사운드포지처럼 피크·RMS·피크 홀드·클립),
스펙트럼, 벡터스코프와 위상 상관을 한 판에 둔다.

움직이지 않는 것(판·눈금·격자)은 크기가 바뀔 때 한 장으로 그려 두고, 매 장에는 그 위에
막대·곡선·점만 GDI 로 얹는다. 그래픽 컨텍스트로 매 장을 다 그리면 무겁다.

장을 넘기는 박자는 wx.Timer 가 아니라 따로 도는 스레드가 잡는다. wx.Timer 는 15.6 ms
경계에 걸려 요청보다 느리게, 고르지 않게 온다(PyMusicPlayer 에서 25 ms 가 31 ms 로 왔다).
'''


import math
import threading
import time
import wx

import numpy

from meter import RATE
from meter import Capture
from meter import to_db
from rackui import FACES
from rackui import RACK
from rackui import draw_faceplate
from rackui import draw_led
from rackui import draw_rails
from rackui import draw_text
from rackui import fill_rect
from rackui import get_font
from rackui import get_short_hz
from rackui import mix
from units import EAR
from units import INSET


# 40 장이면 눈으로는 이어져 보이고, 50 장보다 CPU 를 넉넉히 덜 쓴다.
FPS = 40
MARGIN = 14
HEADER = 30
WIDE_BODY = 128
NARROW = 640
NARROW_METER = 70
NARROW_LOWER = 132

FLOOR = -60.0
METER_CURVE = 0.6
SCALE = (-60, -48, -36, -24, -18, -12, -9, -6, -3, 0)
PEAK_FALL = 24.0
HOLD_TIME = 1.5
HOLD_FALL = 30.0

FFT_SIZE = 4096
SPECTRUM_FLOOR = -90.0
SPECTRUM_FALL = 40.0
SCOPE_SAMPLES = 1536
# 앞 장의 점이 이만큼씩 남는다. 형광 화면처럼 자취가 남아 모양이 읽힌다.
SCOPE_PERSIST = 0.55
SCOPE_DOT = 0.30

# 막대 색. 낮은 쪽은 파랑, 위로 갈수록 호박색·주황 — 초록·빨강 축을 쓰지 않는다.
LOW = '#4c9aff'
MID = '#ffb04d'
HIGH = '#ff7a33'
CLIP = '#ff7a33'


class Pacer(threading.Thread):
    '''정해진 박자로 화면에 한 장을 부탁한다. 앞 장을 다 그리기 전이면 건너뛴다.'''

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
                self.pending = True
                try:
                    wx.CallAfter(self.view.tick)
                except Exception:
                    return


BRUSHES = {}


def get_brush(colour):
    '''같은 몇 가지 색을 한 장에 수십 번 쓴다. 붓은 만들어 둔 것을 돌려 쓴다.'''
    if colour not in BRUSHES:
        BRUSHES[colour] = wx.Brush(wx.Colour(colour))
    return BRUSHES[colour]


class MeterView(wx.Panel):

    def __init__(self, parent, enabled, on_change):
        super().__init__(parent, style=wx.FULL_REPAINT_ON_RESIZE)
        # AutoBufferedPaintDC 로 이미 한 장에 모아 그린다. SetDoubleBuffered(WS_EX_COMPOSITED)를
        # 더하면 50 Hz 마다 옆 창(랙)까지 다시 합성해 CPU 가 몇 배로 뛴다.
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.on_change = on_change
        self.enabled = enabled
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
        self.scope = None
        self.scope_glow = None
        self.scope_gain = 1.0
        self.correlation = 0.0
        self.regions = {}
        self.window = numpy.hanning(FFT_SIZE).astype('float32')
        self.layout_width = None
        self.drawn_quiet = False

        self.Bind(wx.EVT_PAINT, self.on_paint)
        self.Bind(wx.EVT_ERASE_BACKGROUND, lambda event: None)
        self.Bind(wx.EVT_SIZE, self.on_size)
        self.Bind(wx.EVT_LEFT_DOWN, self.on_down)
        self.Bind(wx.EVT_MOTION, self.on_motion)
        if enabled:
            self.start()

    # ------------------------------------------------------------ 켜고 끄기

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
        self.peak = [FLOOR, FLOOR]
        self.hold = [FLOOR, FLOOR]
        self.rms = [FLOOR, FLOOR]
        self.spectrum = None
        self.scope = None
        self.Refresh()

    def set_enabled(self, enabled):
        if enabled == self.enabled:
            return
        self.enabled = enabled
        self.start() if enabled else self.stop()
        self.background_key = None
        self.Refresh()
        self.on_change()

    def close(self):
        if self.pacer is not None:
            self.pacer.running = False
            self.pacer = None
        self.capture.stop()

    # ------------------------------------------------------------ 자리

    def get_height(self, width):
        inner = width - MARGIN * 2
        if inner < NARROW:
            return MARGIN + HEADER + NARROW_METER + 8 + NARROW_LOWER + 12
        return MARGIN + HEADER + WIDE_BODY + 12

    def on_size(self, event):
        width = self.GetClientSize().width
        height = self.get_height(width)
        if self.GetMinSize().height != height:
            self.SetMinSize(wx.Size(-1, height))
            wx.CallAfter(self.GetParent().Layout)
        self.background_key = None
        event.Skip()

    def layout(self, width):
        '''판 안의 세 자리. 좁으면 레벨미터를 위에 한 줄로, 그 아래에 둘을 나란히.'''
        plate = wx.Rect(MARGIN, MARGIN, width - MARGIN * 2, self.get_height(width) - MARGIN)
        left = plate.x + EAR + INSET
        right = plate.x + plate.width - EAR - INSET
        top = plate.y + HEADER
        regions = {'plate': plate, 'power': wx.Rect(left, plate.y + 9, 14, 14)}
        if plate.width < NARROW:
            regions['level'] = wx.Rect(left, top, right - left, NARROW_METER)
            lower = top + NARROW_METER + 8
            size = NARROW_LOWER
            regions['scope'] = wx.Rect(right - size + 26, lower, size - 26, size - 18)
            regions['spectrum'] = wx.Rect(left, lower, right - left - size - 8, size)
        else:
            body = WIDE_BODY
            level_width = round((right - left) * 0.36)
            regions['level'] = wx.Rect(left, top, level_width, body)
            size = body
            regions['scope'] = wx.Rect(right - size + 26, top, size - 26, size - 18)
            spectrum_left = left + level_width + 16
            regions['spectrum'] = wx.Rect(spectrum_left, top,
                                          right - size - 12 - spectrum_left, body)
        scope = regions['scope']
        regions['correlation'] = wx.Rect(scope.x, scope.y + scope.height + 6, scope.width, 10)
        level = regions['level']
        bar = 16
        meter_top = level.y + 18
        regions['bars'] = [wx.Rect(level.x + 14, meter_top + index * (bar + 4),
                                   level.width - 14 - 46, bar) for index in (0, 1)]
        regions['clips'] = [wx.Rect(bar_rect.x + bar_rect.width + 6, bar_rect.y, 40, bar)
                            for bar_rect in regions['bars']]
        self.regions = regions
        return regions

    def to_x(self, rect, db):
        '''0 dB 가까이를 넓게 편다. dB 를 고르게 펴면 -12 위가 손가락 한 마디에 몰린다.'''
        ratio = 1.0 - (min(max(db, FLOOR), 0.0) / FLOOR) ** METER_CURVE
        return rect.x + rect.width * ratio

    # ------------------------------------------------------------ 그림

    def build_background(self, width, height):
        bitmap = wx.Bitmap(max(1, width), max(1, height))
        dc = wx.MemoryDC(bitmap)
        dc.SetBackground(wx.Brush(wx.Colour(RACK['bg'])))
        dc.Clear()
        gc = wx.GraphicsContext.Create(dc)
        regions = self.layout(width)
        plate = regions['plate']
        draw_rails(gc, MARGIN, 0, width - MARGIN * 2, height, EAR)
        face, accent = FACES['master']
        draw_faceplate(gc, plate.x, plate.y, plate.width, plate.height, face, EAR)
        power = regions['power']
        draw_led(gc, power.x + 7, power.y + 7, self.enabled, accent)
        width_title = draw_text(gc, 'OUTPUT', power.x + 22, plate.y + 8, 10.5, RACK['text'],
                                bold=True, engraved=True)[0]
        if plate.width >= NARROW:
            draw_text(gc, 'after Equalizer APO', power.x + 22 + width_title + 10, plate.y + 11,
                      8, RACK['dim'], engraved=True)

        for name in ('level', 'spectrum', 'scope'):
            rect = regions[name]
            if name == 'level':
                continue
            fill_rect(gc, RACK['lcd_rim'], rect.x - 2, rect.y - 2, rect.width + 4,
                      rect.height + 4, 4)
            fill_rect(gc, RACK['lcd'], rect.x, rect.y, rect.width, rect.height, 3)

        # 레벨미터 눈금과 채널 이름.
        for index, bar in enumerate(regions['bars']):
            fill_rect(gc, RACK['lcd_rim'], bar.x - 1, bar.y - 1, bar.width + 2, bar.height + 2, 2)
            fill_rect(gc, '#0a0c0f', bar.x, bar.y, bar.width, bar.height)
            draw_text(gc, 'LR'[index], bar.x - 11, bar.y + 1, 8, RACK['dim'], bold=True,
                      engraved=True)
        first, second = regions['bars']
        for value in SCALE:
            x = round(self.to_x(first, value))
            fill_rect(gc, RACK['faint'], x, second.y + second.height + 3, 1, 4)
            draw_text(gc, str(abs(value)) if value else '0', x, second.y + second.height + 8,
                      7, RACK['dim'], align='center', engraved=True)
        draw_text(gc, 'dB', first.x + first.width + 6 + 20, second.y + second.height + 8, 7,
                  RACK['dim'], align='center', engraved=True)

        spectrum = regions['spectrum']
        inner = self.get_spectrum_inner(spectrum)
        gc.SetPen(wx.Pen(wx.Colour(RACK['lcd_grid']), 1))
        for freq in (50, 100, 200, 500, 1000, 2000, 5000, 10000):
            x = round(self.freq_x(inner, freq)) + 0.5
            gc.StrokeLine(x, inner.y, x, inner.y + inner.height)
            if freq in (100, 1000, 10000):
                draw_text(gc, get_short_hz(freq), x, inner.y + inner.height + 1, 7,
                          RACK['lcd_text'], align='center')
        for db in (-12, -24, -48, -72):
            y = round(self.db_y(inner, db)) + 0.5
            gc.StrokeLine(inner.x, y, inner.x + inner.width, y)
            draw_text(gc, str(db), inner.x - 3, y - 6, 7, RACK['lcd_text'], align='right')

        scope = regions['scope']
        cx, cy = scope.x + scope.width / 2, scope.y + scope.height / 2
        radius = min(scope.width, scope.height) / 2 - 6
        gc.SetPen(wx.Pen(wx.Colour(RACK['lcd_grid']), 1))
        gc.StrokeLine(cx, cy - radius, cx, cy + radius)
        gc.StrokeLine(cx - radius * 0.7, cy - radius * 0.7, cx + radius * 0.7, cy + radius * 0.7)
        gc.StrokeLine(cx + radius * 0.7, cy - radius * 0.7, cx - radius * 0.7, cy + radius * 0.7)
        draw_text(gc, 'L', cx - radius * 0.7 - 2, cy - radius * 0.7 - 4, 7, RACK['lcd_text'],
                  align='right')
        draw_text(gc, 'R', cx + radius * 0.7 + 2, cy - radius * 0.7 - 4, 7, RACK['lcd_text'])
        draw_text(gc, 'M', cx + 4, cy - radius - 1, 7, RACK['lcd_text'])

        correlation = regions['correlation']
        fill_rect(gc, '#0a0c0f', correlation.x, correlation.y, correlation.width,
                  correlation.height, 2)
        middle = correlation.x + correlation.width / 2
        fill_rect(gc, RACK['faint'], middle, correlation.y, 1, correlation.height)
        draw_text(gc, '-1', correlation.x - 3, correlation.y - 1, 7, RACK['dim'], align='right',
                  engraved=True)
        draw_text(gc, '+1', correlation.x + correlation.width + 3, correlation.y - 1, 7,
                  RACK['dim'], engraved=True)
        del gc
        dc.SelectObject(wx.NullBitmap)
        return bitmap

    def get_spectrum_inner(self, rect):
        return wx.Rect(rect.x + 24, rect.y + 6, rect.width - 30, rect.height - 20)

    def freq_x(self, inner, freq):
        return inner.x + inner.width * math.log(freq / 20.0) / math.log(1000.0)

    def db_y(self, inner, db):
        ratio = (min(max(db, SPECTRUM_FLOOR), 0.0) - SPECTRUM_FLOOR) / -SPECTRUM_FLOOR
        return inner.y + inner.height * (1 - ratio)

    def on_paint(self, event):
        dc = wx.AutoBufferedPaintDC(self)
        width, height = self.GetClientSize()
        key = (width, height, self.enabled)
        if self.background is None or self.background_key != key:
            self.background = self.build_background(width, height)
            self.background_key = key
        dc.DrawBitmap(self.background, 0, 0)
        if not self.regions:
            return
        self.draw_levels(dc)
        self.draw_spectrum(dc)
        self.draw_scope(dc)
        self.draw_status(dc)

    def draw_status(self, dc):
        plate = self.regions['plate']
        right = plate.x + plate.width - EAR - INSET
        if not self.enabled:
            text = 'Meters off'
        elif self.capture.error:
            text = self.capture.error
        else:
            text = self.capture.device
        dc.SetFont(get_font(8))
        dc.SetTextForeground(wx.Colour(RACK['warn'] if self.capture.error else RACK['dim']))
        limit = plate.width // 2 if plate.width >= NARROW else plate.width - EAR * 2 - 120
        while text and dc.GetTextExtent(text)[0] > limit:
            text = text[:-2] + '…'
        dc.DrawText(text, right - dc.GetTextExtent(text)[0], plate.y + 11)

    def get_colour(self, db):
        if db >= -3:
            return HIGH
        if db >= -12:
            return MID
        return LOW

    def draw_levels(self, dc):
        regions = self.regions
        dc.SetPen(wx.TRANSPARENT_PEN)
        for channel, bar in enumerate(regions['bars']):
            rms_x = self.to_x(bar, self.rms[channel])
            peak_x = self.to_x(bar, self.peak[channel])
            # 피크는 밝게, RMS 는 그 안쪽에 진하게 — 두 막대를 한 칸에 겹친다.
            for low, high, colour in ((FLOOR, -12, LOW), (-12, -3, MID), (-3, 0, HIGH)):
                start = self.to_x(bar, low)
                end = min(peak_x, self.to_x(bar, high))
                if end > start:
                    dc.SetBrush(get_brush(mix(colour, '#000000', 0.45).GetAsString(wx.C2S_HTML_SYNTAX)))
                    dc.DrawRectangle(round(start), bar.y + 1, round(end - start) + 1,
                                     bar.height - 2)
                end = min(rms_x, self.to_x(bar, high))
                if end > start:
                    dc.SetBrush(get_brush(colour))
                    dc.DrawRectangle(round(start), bar.y + 3, round(end - start) + 1,
                                     bar.height - 6)
            if self.hold[channel] > FLOOR:
                x = round(self.to_x(bar, self.hold[channel]))
                dc.SetBrush(get_brush('#f2f4f6'))
                dc.DrawRectangle(x - 1, bar.y + 1, 2, bar.height - 2)

            clip = regions['clips'][channel]
            lit = self.clips[channel]
            dc.SetBrush(get_brush(CLIP if lit else '#1a1c20'))
            dc.DrawRoundedRectangle(clip, 2)
            dc.SetFont(get_font(7.5, bold=True))
            text = 'CLIP' if lit else ('%.1f' % self.hold[channel]
                                       if self.hold[channel] > FLOOR else '-inf')
            dc.SetTextForeground(wx.Colour('#101215' if lit else RACK['text']))
            width, height = dc.GetTextExtent(text)
            dc.DrawText(text, clip.x + (clip.width - width) // 2,
                        clip.y + (clip.height - height) // 2)

        level = regions['level']
        dc.SetFont(get_font(7.5))
        dc.SetTextForeground(wx.Colour(RACK['dim']))
        text = 'RMS %s / %s' % (self.format_db(self.rms[0]), self.format_db(self.rms[1]))
        dc.DrawText(text, level.x + 14, level.y)

    def format_db(self, value):
        return '-inf' if value <= FLOOR else '%.1f' % value

    def draw_spectrum(self, dc):
        if self.spectrum is None:
            return
        rect = self.regions['spectrum']
        inner = self.get_spectrum_inner(rect)
        xs, values = self.spectrum
        points = [wx.Point(round(x), round(self.db_y(inner, value))) for x, value in zip(xs, values)]
        bottom = inner.y + inner.height
        polygon = [wx.Point(points[0].x, bottom)] + points + [wx.Point(points[-1].x, bottom)]
        dc.SetClippingRegion(inner)
        dc.SetPen(wx.TRANSPARENT_PEN)
        dc.SetBrush(wx.Brush(wx.Colour(mix(LOW, RACK['lcd'], 0.62))))
        dc.DrawPolygon(polygon)
        dc.SetPen(wx.Pen(wx.Colour(LOW), 1))
        dc.DrawLines(points)
        dc.DestroyClippingRegion()

    def draw_scope(self, dc):
        regions = self.regions
        if self.scope is not None:
            scope = regions['scope']
            dc.DrawBitmap(self.scope, scope.x, scope.y)
        correlation = regions['correlation']
        x = correlation.x + correlation.width * (self.correlation + 1) / 2
        dc.SetPen(wx.TRANSPARENT_PEN)
        dc.SetBrush(get_brush(LOW if self.correlation >= 0 else MID))
        dc.DrawRectangle(round(x) - 2, correlation.y + 1, 4, correlation.height - 2)

    # ------------------------------------------------------------ 한 장

    def tick(self):
        # 창을 닫은 뒤에도 이미 줄 서 있던 부탁이 한 번 더 올 수 있다. 지워진 창은 거짓이다.
        if not self:
            return
        if self.pacer is not None:
            self.pacer.pending = False
        if not self.enabled or not self.regions or not self.IsShownOnScreen():
            return
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
        self.update_spectrum(recent, elapsed)
        self.update_scope(recent[-SCOPE_SAMPLES:])
        # 소리가 없고 모든 계기가 바닥에 닿았으면 같은 그림을 다시 그리지 않는다.
        quiet = (max(peaks) == 0.0 and max(self.peak) <= FLOOR and max(self.hold) <= FLOOR and
                 (self.spectrum is None or self.spectrum[1].max() <= SPECTRUM_FLOOR))
        if quiet and self.drawn_quiet:
            return
        self.drawn_quiet = quiet
        # 판 머리와 레일은 그대로다. 움직이는 칸만 다시 그리게 해 화면으로 옮기는 양을 줄인다.
        plate = self.regions['plate']
        self.RefreshRect(wx.Rect(plate.x + EAR, plate.y + 4, plate.width - EAR * 2,
                                 plate.height - 6), False)

    def update_spectrum(self, recent, elapsed):
        inner = self.get_spectrum_inner(self.regions['spectrum'])
        if inner.width < 8:
            return
        mono = recent.mean(axis=1) * self.window
        magnitude = numpy.abs(numpy.fft.rfft(mono)) * (4.0 / FFT_SIZE)
        freqs = numpy.fft.rfftfreq(FFT_SIZE, 1.0 / RATE)
        columns = max(16, inner.width // 4)
        edges = 20.0 * numpy.power(1000.0, numpy.linspace(0, 1, columns + 1))
        # 저역은 한 칸에 FFT 칸이 하나도 안 들 만큼 좁다. 적어도 하나씩은 물리게 민다.
        starts = numpy.minimum(numpy.searchsorted(freqs, edges[:-1]), len(magnitude) - 1)
        values = numpy.maximum.reduceat(magnitude, starts)
        stops = numpy.searchsorted(freqs, edges[1:])
        narrow = stops <= starts
        values[narrow] = magnitude[starts[narrow]]
        values = 20 * numpy.log10(numpy.maximum(values, 1e-9))
        if self.spectrum is not None and len(self.spectrum[1]) == columns:
            values = numpy.maximum(values, self.spectrum[1] - SPECTRUM_FALL * elapsed)
        centres = numpy.sqrt(edges[:-1] * edges[1:])
        xs = [self.freq_x(inner, freq) for freq in centres]
        self.spectrum = (xs, values)

    def update_scope(self, block):
        scope = self.regions['scope']
        left, right = block[:, 0], block[:, 1]
        energy = float(numpy.sqrt((left ** 2 + right ** 2).mean()))
        # 점들이 늘 화면을 알맞게 채우도록 이득을 천천히 따라 맞춘다.
        target = min(8.0, 0.35 / max(energy, 1e-4))
        self.scope_gain += (target - self.scope_gain) * 0.15
        radius = min(scope.width, scope.height) / 2 - 6
        width, height = scope.width, scope.height
        side = (right - left) * 0.7071 * radius * self.scope_gain
        mid = (right + left) * 0.7071 * radius * self.scope_gain
        # 점을 하나씩 찍으면 한 장에 3 ms 가 든다. 작은 밝기 판에 모아 한 장으로 붙인다.
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
        denominator = float(numpy.sqrt((left ** 2).sum() * (right ** 2).sum()))
        if denominator > 1e-9:
            value = float((left * right).sum()) / denominator
            self.correlation += (value - self.correlation) * 0.25

    def paint_glow(self, glow):
        '''밝기 판을 LCD 바탕에서 점 색까지 섞어 비트맵으로. 격자는 그 아래 바탕에 있어
        점이 없는 자리만 비쳐 보이게 0 인 칸은 바탕과 같은 색이 아니라 투명으로 둔다.'''
        height, width = glow.shape
        base = numpy.array(wx.Colour(RACK['lcd']).Get()[:3], dtype='float32')
        dot = numpy.array(wx.Colour(mix(LOW, '#ffffff', 0.3)).Get()[:3], dtype='float32')
        level = glow[..., None]
        rgb = (base + (dot - base) * level).astype('uint8')
        alpha = (numpy.minimum(1.0, glow * 4) * 255).astype('uint8')
        return wx.Bitmap.FromBufferRGBA(width, height,
                                        numpy.dstack([rgb, alpha[..., None]]).tobytes())

    # ------------------------------------------------------------ 마우스

    def hit(self, point):
        if not self.regions:
            return None
        if wx.Rect(self.regions['power']).Inflate(4, 4).Contains(point):
            return 'power'
        for clip in self.regions['clips']:
            if clip.Contains(point):
                return 'clip'
        return None

    def on_down(self, event):
        target = self.hit(event.GetPosition())
        if target == 'power':
            self.set_enabled(not self.enabled)
        elif target == 'clip':
            self.capture.reset_clips()
            self.clips = [False, False]
            self.hold = [FLOOR, FLOOR]
            self.Refresh(False)

    def on_motion(self, event):
        target = self.hit(event.GetPosition())
        self.SetCursor(wx.Cursor(wx.CURSOR_HAND if target else wx.CURSOR_ARROW))
        tip = {'power': 'Meters on/off', 'clip': 'Click to reset'}.get(target, '')
        if tip != (self.GetToolTipText() or ''):
            self.SetToolTip(tip or None)
