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


# 30 장이면 막대와 곡선이 눈으로 이어져 보인다. 40 장이던 때보다 CPU 를 4 분의 1 덜 쓴다.
FPS = 30
# 창 위·좌우·아래 여백. 14 는 넓어 보였다(사용자) — 스크롤바(폭 4 + 안쪽 3)가 들어갈 만큼만.
# 위 여백은 핀을 꽂아 창 맨 위에 설 때만 둔다. 핀을 빼면 랙 맨 아래 칸이라 위는 장치 사이 GAP 이다.
MARGIN = 8
# 계기판은 판 하나, 화면 하나다(사용자). 화면 안에 LEVEL · PHASE · SPECTRUM · BARS 구역이
# 가는 금으로 나뉘어 쌓이고, 이름 띠의 토글 단추로 구역마다 보이고 숨긴다. 차례는 미터,
# 막대 띠, 분석기(사용자 지정). 화면 테두리는 판 가장자리·띠 아래 금에서 TIGHT_PAD.
# 화면 안 차례이자 토글 단추 차례. 분석기는 맨 아래(사용자).
# 오실로스코프와 스펙트로그램은 그다음(사용자 요청 10/11).
PARTS = ('level', 'spectrum', 'oscilloscope', 'spectrogram')
# 판 이름. OUTPUT 이라 하면 끄면 소리가 안 나갈 것처럼 읽혀(사용자) 재는 판임을 드러낸다.
TITLE = 'Analyzer'
# 'level' 구역에는 레벨·스코프·막대 띠·상관·균형이 다 있어 LEVEL 은 이름이 좁다(사용자).
PART_LABELS = {'level': 'METERS', 'spectrum': 'SPECTRUM', 'oscilloscope': 'SCOPE',
               'spectrogram': 'SPECTROGRAM'}
# LEVEL 구역: 왼쪽 정사각 벡터스코프, 오른쪽에 L·R / 눈금 / M·S·I / 상관·균형 줄(사용자).
# 막대 띠는 낮게(사용자: 높으면 보기 싫다 → 40 은 작다 → 52 는 조금 크다 → 46). 위상도 110 → 96.
# 두 구역 키는 같게(사용자).
# 창이 좁아 칩이 PIN 에 닿으면 쓰는 짧은 이름.
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
# 분석기: 1 kHz 를 축으로 옥타브마다 +3 dB 기울여 음악이 평평하게 보이게. 곡선은 시간으로
# 고르게 하고, 피크 선은 1 초 머문 뒤 초당 12 dB 로 내린다.
SPECTRUM_TILT = 3.0
SPECTRUM_SMOOTH = 0.35
PEAK_LINE_HOLD = 1.0
PEAK_LINE_FALL = 12.0
SPECTRUM_FREQS = (20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000)
SPECTRUM_DBS = (0, -12, -24, -36, -48, -60, -72, -84)
SCOPE_SAMPLES = 1536

# 오실로스코프: 스펙트로그램과 같은 시간축(사용자) — 한 장마다 오른쪽에 한 열, 그 장 사이 표본의
# 가장 높은·낮은 값(옅게)과 RMS(밝게). 40 ms 파형은 믹스된 음악에서 잡음처럼만 보였다. 크기는 고정
# (위아래 끝 = 0 dBFS)이라 시간에 따른 세기를 그대로 읽는다.
# 스펙트로그램: 한 장마다 오른쪽에 한 줄을 붙이고 왼쪽으로 민다. 세로는 분석기와 같은 로그
# 주파수, 같은 기울기.
GRAM_LOW = -84.0
GRAM_HIGH = -12.0
# 색은 inferno(matplotlib) 단계 — 바탕 → 보라 → 빨강·주황 → 노랑 → 흰빛(사용자). 초록이 거의 없고 밝기가
# 끝까지 오르기만 해 적록색약에서도 세기가 읽힌다. 0 은 LCD 바탕색으로 두어 빈 자리가 화면과 같다.
GRAM_STOPS = ((0.0, '#111215'), (0.125, '#1f0c48'), (0.25, '#57106e'), (0.375, '#8a226a'),
              (0.5, '#bc3754'), (0.625, '#e45a31'), (0.75, '#f98e09'), (0.875, '#f6d746'),
              (1.0, '#fcffa4'))
GRAM_FREQS = (100, 1000, 10000)

# PyMusicPlayer 의 스펙트럼(playbox.PlayBoxSpectrum · audio.get_stream_spectrum_vectorscope)을
# 그대로 옮긴 것. 75 ms 를 10 Hz 칸으로 풀고, 반음마다 막대 하나를 가운데에서 위아래로 세운다.
# 그쪽은 BASS_ChannelGetData 에 길이를 바이트로 넘긴다(fs · 0.075 바이트). 16 비트 스테레오라
# 실제로 들어가는 것은 채널마다 그 4 분의 1 — 48 kHz 에서 900 표본(19 ms)이다. 크기도 이것에
# 맞춰져 있어 길게 잡으면 막대가 넘친다. 버퍼 나머지 절반에 남는 초기값(arange)은 따르지 않는다.
BAR_FRAME = int(RATE * 0.075 / 4)
BAR_POINTS = int(RATE * 0.1)
BAR_LOW_PAD = (2, 3, 4, 5, 6, 7)
# PyMusicPlayer 의 반음 표. 8 Hz, 8.4 Hz 다음부터는 8.9 Hz 에서 반음씩 오른다.
BAR_NOTES = [8.0, 8.41536811017449] + [8.91577193817796 * 2 ** (step / 12)
                                       for step in range(127)]
BAR_HEIGHT = 0.4
# 900 표본이면 실제 분해능은 53 Hz 인데 0 을 덧대 10 Hz 칸으로 푼다. 저역 막대가 한두 칸만
# 보면 막대마다 봉우리와 골에 번갈아 걸려 빗살 같은 틈이 생긴다. 적어도 앞뒤 이만큼은 본다.
BAR_REACH = 3
# PyMusicPlayer 는 곡을 열 때 고역(5 kHz 위) RMS 로 autogain = 0.14 / (3 · RMS) 를 정한다.
# 여기는 곡을 미리 못 보니 나가는 소리로 같은 값을 재고 천천히 따라간다. 기본값도 같은 0.4.
AUTOGAIN_DEFAULT = 0.4
AUTOGAIN_RANGE = (0.05, 4.0)
AUTOGAIN_FOLLOW = 2.0


def get_firwin(taps, cutoff, highpass):
    '''scipy.signal.firwin 과 같은 해밍 창 sinc. 그쪽 저역 통과는 0 Hz, 고역 통과는 나이퀴스트
    에서 이득이 1 이 되게 맞춘다. scipy 를 들이지 않으려고 옮겨 왔다.'''
    middle = numpy.arange(taps) - (taps - 1) / 2
    if highpass:
        response = numpy.sinc(middle) - cutoff * numpy.sinc(cutoff * middle)
    else:
        response = cutoff * numpy.sinc(cutoff * middle)
    response *= numpy.hamming(taps)
    return response / (response * numpy.cos(numpy.pi * middle * (1.0 if highpass else 0.0))).sum()


def get_autogain_weights():
    '''mfeats 가 autogain 을 재기 전에 거는 필터 사슬을 주파수 응답으로 바꿔 둔다. 시간 축에서
    거르지 않고 FFT 칸마다 이 무게를 곱하면 같은 에너지가 나온다.'''
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
# 막대 한 벌의 수와 바라는 간격. 막대 폭은 넓어져도 1 화소 그대로다(사용자: 뚱뚱해지지 않게).
BAR_SET = 103
BAR_PITCH = 3
BAR_WIDTH = 1
# 앞 장의 점이 이만큼씩 남는다. 형광 화면처럼 자취가 남아 모양이 읽힌다.
SCOPE_PERSIST = 0.55
SCOPE_DOT = 0.30

# 막대 색. 낮은 쪽은 파랑, 위로 갈수록 호박색·주황 — 초록·빨강 축을 쓰지 않는다.
LOW = '#4c9aff'
# 막대 색은 레벨 막대와 같은 파랑 한 색(사용자: 흰 막대만 떠 보였다 → 섞으면 뿌옇다 → 높이에 따라
# 바꾸지 말고 한 색으로).
# 막대 무리(레벨·CORR·BAL·스펙트럼 막대)의 파랑. LOW 를 흰색 쪽으로 75 % — 1 화소 칸은 같은 색도
# 어둡게 읽혀 더 희게(사용자: 18·30·45·60 % 도 어둡다). 막대 끝을 바탕 쪽으로 섞으면 뿌옇다(사용자).
METER_BLUE = '#d2e6ff'
# 선·점(벡터스코프·스펙트럼 곡선·SCOPE 파형)의 파랑 — METER_BLUE 에 LOW 를 35 % 남긴 색. 막대보다 한
# 단계 낮아야 점이 몰린 자리가 하얗게 뜨지 않는다(사용자). 세 곳이 한 톤(사용자).
TRACE_BLUE = '#a3cbff'
BAR_COLOUR = METER_BLUE
MID = '#ffb04d'
HIGH = '#ff7a33'
CLIP = '#ff7a33'
# 막대 무리의 주황 둘도 흰색 쪽으로 — 1 화소 칸에서 피크 쪽이 어두웠다(사용자). 60 % 는 붉은 기가 빠져
# 더 붉게(사용자): -9~-3 은 25 %, -3 위는 15 % 만 섞는다.
METER_MID = '#ffc47a'
METER_HIGH = '#ff8e52'
# 칸으로 나뉜 LED 막대. 꺼진 칸도 제 색을 옅게 남겨 기기처럼 보이게.
SEGMENT_OFF = 0.84
# RMS 위 순간 피크까지의 칸도 같은 밝기 — 0.42·0.15 로 어둡게 하면 피크 쪽이 어두웠다(사용자: 더 밝게).
SEGMENT_HALF = 0.0
# 가로 미터. 줄마다 가는 막대 하나(6 화소), 칸은 1 화소 + 틈 2 화소. 위 두 줄 L·R,
# 가운데 눈금 줄, 아래 세 줄 M·S·I(라우드니스). 오른쪽에 숫자 두 칸.
BAR = 6
ROW = 12
METER_FLOOR = -48.0
METER_SCALE = (0, -3, -6, -9, -12, -18, -24, -30, -36, -42, -48)
# 칸 1 화소, 틈 2 화소 — 스펙트럼 막대(1 화소, 3 화소 간격)와 같은 결·같은 밝기(사용자). 2/1 일 때는
# 같은 색인데도 막대 띠만 어두워 보였다(칠한 면적 1/3 대 2/3).
SEGMENT = 1
SEGMENT_GAP = 2
# 이름 칸(L·R·M·S·I). 막대 오른쪽 끝, 클립 표시 다음에 선다 — 왼쪽은 스코프만 남아 가운데
# 막대가 길어진다(사용자). 글자 폭이 달라도 칸 가운데에 선다.
NAME_WIDTH = 12
# 막대 끝 → 클립(4) → 이름 칸 → 숫자 두 칸. 숫자 칸은 '-12.3' 이 들어갈 만큼만.
CLIP_GAP = 4
CLIP_WIDTH = 4
NAME_GAP = 4
READOUT = 34
LOUDNESS_NAMES = {'M': 'MOM', 'S': 'SHORT', 'I': 'INT'}
PHASE_NAMES = {'correlation': 'CORR', 'balance': 'BAL'}
# 레벨 구역 안 저자 막대 띠의 안쪽 키. 막대는 가운데에서 위아래로 선다.
STRIP_HEIGHT = 24
# 벡터스코프 자리(정사각). 구역 키 118 보다 작아 위아래에 7 씩 남는다.
SCOPE_SIDE = 104
BALANCE_RANGE = 6.0
LOUDNESS_COLOURS = {'M': '#4c9aff', 'S': '#8cc8ff', 'I': '#ffb04d'}
READOUT_FONT = 'Consolas'
LOUDNESS_EVERY = 0.5
NOTE_NAMES = ('C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B')


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
MONO = {}


def get_mono(size):
    '''숫자 칸 글씨. 자릿수가 바뀌어도 숫자가 춤추지 않게 고정폭.'''
    if size not in MONO:
        MONO[size] = wx.Font(wx.FontInfo(size).FaceName(READOUT_FONT).Bold())
    return MONO[size]


def get_brush(colour):
    '''같은 몇 가지 색을 한 장에 수십 번 쓴다. 붓은 만들어 둔 것을 돌려 쓴다.'''
    if colour not in BRUSHES:
        BRUSHES[colour] = wx.Brush(wx.Colour(colour))
    return BRUSHES[colour]


class MeterView(wx.Panel):

    def __init__(self, parent, on_change, folded=False, pinned=True, parts=None):
        super().__init__(parent, style=wx.FULL_REPAINT_ON_RESIZE)
        # AutoBufferedPaintDC 로 이미 한 장에 모아 그린다. SetDoubleBuffered(WS_EX_COMPOSITED)를
        # 더하면 50 Hz 마다 옆 창(랙)까지 다시 합성해 CPU 가 몇 배로 뛴다.
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
        self.autogain = AUTOGAIN_DEFAULT
        self.scope = None
        self.scope_glow = None
        self.scope_gain = 1.0
        self.wave = None
        self.wave_dark = 0
        self.gram = None
        self.gram_rows = None
        self.gram_dark = 0
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
        # 분석기 위에 올린 마우스 x. 그 자리의 주파수·음이름·dB 를 읽어 준다.
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
        # 구역마다 숨겼는지. 숨긴 구역은 셈도 하지 않는다.
        self.parts = {name: bool((parts or {}).get(name)) for name in PARTS}
        if all(self.parts.values()):
            self.parts = {name: False for name in PARTS}
        # 오른쪽 여백. 핀을 빼면 판이 랙 위에 겹쳐 놓이는데, 여백까지 덮으면 랙 스크롤바의 윗
        # 부분이 판 뒤에 숨어 굴릴 때 막대가 늘었다 줄었다 하는 것처럼 보였다. 그때는 주 창이
        # 여백만큼 좁게 놓고 이 값을 0 으로 둔다.
        self.right_margin = MARGIN
        self.left_margin = MARGIN
        # 넓은 창에서 랙이 여러 단이면 이 판도 랙의 한 칸으로 단에 들어간다. 그때 핀은 맨 앞에
        # 둘지 맨 끝에 둘지만 정하고, 판은 랙과 함께 구른다.
        self.flowing = False
        # 판의 키나 핀이 바뀌면 부르는 자리. 판을 놓는 쪽(주 창)이 채운다.
        self.on_height = lambda: None
        if self.is_running():
            self.start()

    # ------------------------------------------------------------ 켜고 끄기

    def is_running(self):
        '''켜져 있고 펼쳐져 있을 때만 받고 그린다. 접어 두면 CPU 를 쓰지 않는다.'''
        # 켜고 끄는 단추는 없다. 펼치면 재고, 접으면 멈춘다(사용자) — 소리에는 손대지 않는다.
        return not self.folded and not all(self.parts.values())

    def is_open(self, name):
        return not self.folded and not self.parts[name]

    def set_part_hidden(self, name, folded):
        if self.parts[name] == folded:
            return
        # 구역을 모두 끌 수는 없다. 마지막 하나를 끄면 다른 구역이 켜진다(사용자).
        if folded and all(self.parts[other] for other in PARTS if other != name):
            for other in PARTS:
                if other != name:
                    self.parts[other] = False
        self.parts[name] = folded
        self.start() if self.is_running() else self.stop()
        self.SetMinSize(wx.Size(-1, self.get_height(self.GetClientSize().width)))
        self.background_key = None
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
        self.clear()
        self.Refresh()

    def clear(self):
        '''끈 뒤에 앞서 받은 소리가 한 칸이라도 남지 않게 계기 값을 모두 비운다.'''
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

    # ------------------------------------------------------------ 자리

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
        # Auto Master 칩과 같은 GC 로 잰다. DC 로 재면 1 화소 어긋난다.
        dc = wx.MemoryDC(wx.Bitmap(1, 1))
        return get_chip_width(wx.GraphicsContext.Create(dc), text)

    def layout(self, width):
        '''이름 띠: 접기 · 켜기 · 제목 · 구역 토글 단추들 … 장치 이름 · PIN. 그 아래 화면 하나에
        보이는 구역만 차례로 쌓고 사이에 금 한 줄. 화면 테두리는 판 가장자리와 띠 아래 금에서
        PAD 만큼 떨어진다.'''
        plate = wx.Rect(self.left_margin, self.get_top(),
                        width - self.left_margin - self.right_margin,
                        self.get_height(width) - self.get_top())
        left = plate.x + PAD
        right = plate.x + plate.width - PAD
        middle = plate.y + FOLDED // 2
        regions = {'plate': plate, 'fold': wx.Rect(left - 4, middle - FOLD // 2, FOLD, FOLD),
                   'icon': wx.Rect(left + FOLD, middle - 7, 14, 14),
                   'pin': wx.Rect(right - PIN_WIDTH + 2, middle - PIN // 2, PIN_WIDTH, PIN),
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
        # 화면 테두리는 화면 1 화소 바깥에 그린다. 테두리가 TIGHT_PAD 에 닿게 한 칸 들인다.
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
            # 화면 테두리 몫 2 화소를 구역마다 고르게 덜어 같은 키의 구역은 같게 보인다.
            trim = 2 // len(shown) + (1 if index < 2 % len(shown) else 0)
            height = PART_BODIES[name] - trim
            sections[name] = wx.Rect(body.x, y, body.width, height)
            y += height
        for name in ('spectrum', 'oscilloscope', 'spectrogram'):
            if name in sections:
                regions[name] = sections[name]
        if 'level' in sections:
            # 레벨 구역 왼쪽에 정사각 벡터스코프, 가는 세로 금, 그 오른쪽에 미터(사용자).
            # 막대 왼쪽(스코프·이름)과 오른쪽(숫자) 자리는 언제나 같은 폭 — 막대가 화면
            # 가운데 선다(사용자). 창 폭에 따라 늘고 주는 것은 가운데 막대뿐이다.
            section = sections['level']
            names = 1 + LCD_PAD
            readout = (CLIP_GAP + CLIP_WIDTH + NAME_GAP + NAME_WIDTH + NAME_GAP + READOUT * 2 +
                       LCD_PAD)
            # 스코프는 언제나 같은 크기의 정사각(사용자: 화면이 작아져도 원래 비율 그대로),
            # 구역 키보다 조금 작게 세로 가운데에 둔다 — 그만큼 가운데 막대가 길어진다(사용자).
            # 좁아지면 스코프 대신 가운데 막대가 줄어든다.
            side = min(SCOPE_SIDE, section.height)
            wing = max(readout, side + names)
            regions['scope'] = wx.Rect(section.x + 4, section.y + (section.height - side) // 2 + 4,
                                       side - 8, side - 8)
            regions['scope_divider'] = wx.Rect(section.x + side, section.y + LCD_PAD, 1,
                                               section.height - LCD_PAD * 2)
            # 칸 끝의 틈 한 화소까지 셈해 보이는 막대가 정확히 가운데.
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
        '''막대 | 클립 · 이름 칸 | 숫자 두 칸. L·R 다음 눈금 줄, 그 아래 막대 띠(M·S·I 는 숫자), 상관·균형.'''
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
        # 상관·균형은 dB 막대가 아니라 가운데에서 좌우로 가는 막대. 이름 칸은 비운다.
        regions['correlation'] = rows.pop('C')
        regions['balance'] = rows.pop('B')
        regions['phase_boxes'] = {'correlation': boxes.pop('C'), 'balance': boxes.pop('B')}
        # M·S·I 막대 자리에는 저자 막대 띠를 둔다(사용자). 라우드니스는 오른쪽 숫자로만 읽는다.
        # 띠의 안쪽(get_bars_inner)이 L·R 막대와 같은 좌우 끝, M 위 끝~I 아래 끝을 덮게.
        # 띠 키는 STRIP_HEIGHT(사용자: 더 낮게). 오른쪽 숫자 세 줄 높이의 가운데에 놓는다.
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
        # 상관·균형 줄도 같은 칸을 쓴다(사용자: 칸 있는 막대로 일관). 가운데 칸이 0 이다.
        xs = [segment[0] for segment in regions['segments']]
        regions['phase_segments'] = xs
        regions['phase_middle'] = len(xs) // 2

    def get_segments(self, row):
        '''왼쪽에서 오른쪽으로 칸마다 (x, 그 칸이 켜지는 dB, 색, 반쯤 켠 색).'''
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

    # ------------------------------------------------------------ 그림

    def build_background(self, width, height):
        bitmap = wx.Bitmap(max(1, width), max(1, height))
        dc = wx.MemoryDC(bitmap)
        dc.SetBackground(wx.Brush(wx.Colour(RACK['bg'])))
        dc.Clear()
        gc = wx.GraphicsContext.Create(dc)
        regions = self.layout(width)
        plate = regions['plate']
        draw_rails(gc, self.left_margin, 0, width - self.left_margin - self.right_margin, height,
                   EAR)
        face, accent = FACES['master']

        # 이름 띠 — 랙의 장치와 같은 자리, 같은 글씨. 접어도 같다.
        draw_faceplate(gc, plate.x, plate.y, plate.width, plate.height, face, EAR, accent)
        power, fold = regions['icon'], regions['fold']
        # 머리 띠 단추는 랙의 것과 같은 반응 — 올리면 바탕 칸과 밝은 글리프(사용자: 일관성).
        hover = getattr(self, 'hover_target', None)
        if hover == 'fold':
            fill_rect(gc, RACK['button_hover'], fold.x, fold.y, fold.width, fold.height, 3)
        draw_glyph(gc, 'right' if self.folded else 'down', fold.x + fold.width / 2,
                   fold.y + fold.height / 2, 10, RACK['text'] if hover == 'fold' else RACK['dim'])
        # 누르는 단추가 아닌 표시는 회색. 장치 색은 누를 수 있는 것(켜진 불·켜진 단추)에만.
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
        return bitmap

    def draw_icon(self, gc, rect, accent):
        '''불 자리에 세운 계기 표시: 높이가 다른 막대 셋. 누르는 단추가 아니다.'''
        bottom = rect.y + rect.height - 2
        for index, height in enumerate((6, 11, 8)):
            fill_rect(gc, accent, rect.x + 2 + index * 4, bottom - height, 2, height, 1)

    def draw_pin(self, gc, rect, accent):
        draw_chip(gc, rect, 'PIN', self.pinned, getattr(self, 'hover_target', None) == 'pin')


    def draw_level_ground(self, gc, regions):
        '''눈금 금과 글씨, 꺼진 칸, 이름, 숫자 칸 이름. 켜진 칸과 숫자만 매 장 얹는다.'''
        rows = regions['rows']
        first, last = rows['L'], rows['R']
        scale_y = regions['scale_y']
        # 좁으면 0 쪽 글씨가 서로 겹친다. 0 부터 왼쪽으로 가며 앞 글씨와 18 화소 안이면 건너뛴다.
        drawn = None
        for value in METER_SCALE:
            x = round(self.to_x(first, value))
            fill_rect(gc, RACK['lcd_axis'] if value == 0 else RACK['lcd_grid'], x, first.y - 2,
                      1, last.y + last.height + 2 - (first.y - 2))
            # 맨 왼쪽 -48 은 눈금에서 시작하게(가운데 맞춤이면 '-' 가 왼쪽 세로 금에 붙는다).
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
        # 숫자 칸 이름도 숫자와 같은 고정폭 글씨로. 비례 글씨는 글자 모양마다 오른쪽 끝이
        # 1~2 화소씩 달라 숫자와 끝이 어긋나 보였다.
        gc.SetFont(get_mono(6.5), wx.Colour(RACK['faint']))
        labels = [(boxes['Lpk'].x + boxes['Lpk'].width + 1, scale_y + 1, 'PK'),
                  (boxes['Lrms'].x + boxes['Lrms'].width + 1, scale_y + 1, 'RMS')]
        labels += [(boxes[key].x + boxes[key].width * 2, boxes[key].y + 1, text)
                   for key, text in LOUDNESS_NAMES.items()]
        labels += [(box.x + box.width * 2, box.y + 1, PHASE_NAMES[key])
                   for key, box in regions['phase_boxes'].items()]
        for x, y, text in labels:
            # 고정폭 칸은 글자 잉크가 칸 끝보다 한 화소 안쪽에서 끝난다(실측). 숫자에 맞춰 민다.
            gc.DrawText(text, x - gc.GetTextExtent(text)[0] + 1, y)
        for clip in regions['clips']:
            fill_rect(gc, RACK['lcd_grid'], clip.x, clip.y, clip.width, clip.height)

    def draw_spectrum_ground(self, gc, regions):
        '''분석기 격자. 주파수는 20 Hz 에서 20 kHz 까지 로그로, dB 는 12 마다.'''
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
        '''가운데 0 줄은 밝게, 반 크기(-6 dBFS) 줄은 격자 색.'''
        inner = self.get_wave_inner(regions['oscilloscope'])
        for y in (inner.y + inner.height // 4, inner.y + inner.height * 3 // 4):
            fill_rect(gc, RACK['lcd_grid'], inner.x, y, inner.width, 1)
        fill_rect(gc, RACK['lcd_axis'], inner.x, inner.y + inner.height // 2, inner.width, 1)

    def draw_gram_labels(self, dc, inner):
        dc.SetFont(get_font(6.5))
        dc.SetTextForeground(wx.Colour(RACK['lcd_text']))
        for freq in GRAM_FREQS:
            y = round(self.gram_y(inner, freq))
            text = get_short_hz(freq)
            width, height = dc.GetTextExtent(text)
            # 왼쪽(가장 오래된 쪽)에 둔다. 오른쪽에 두면 막 들어온 소리를 가렸다.
            dc.DrawText(text, inner.x + 4, y - height // 2)

    def gram_y(self, inner, freq):
        '''스펙트로그램 세로 자리. 아래가 20 Hz, 위가 20 kHz.'''
        ratio = math.log(min(max(freq, 20.0), 20000.0) / 20.0) / math.log(1000.0)
        return inner.y + inner.height - 1 - (inner.height - 1) * ratio

    def draw_spectrum_labels(self, dc, inner):
        '''눈금 글씨는 그래프 안에 얹는다 — Hz 는 아래 끝 줄, dB 는 오른쪽 끝 줄. 바깥에 글씨
        띠를 두면 좌우 여백이 달라 보였다(사용자). 곡선 위에 그려 채움에 묻히지 않게 한다.
        맨 아래 dB 줄은 Hz 글씨와 겹쳐 글씨를 달지 않는다.'''
        dc.SetFont(get_font(6.5))
        dc.SetTextForeground(wx.Colour(RACK['lcd_text']))
        bottom = inner.y + inner.height
        last = len(SPECTRUM_FREQS) - 1
        for index, freq in enumerate(SPECTRUM_FREQS):
            x = round(self.freq_x(inner, freq))
            text = get_short_hz(freq)
            width, height = dc.GetTextExtent(text)
            left = x + 3 if index == 0 else x - width - 3 if index == last else x - width // 2
            dc.DrawText(text, left, bottom - height - 2)
        # 키가 낮아 글씨 줄 사이가 16 보다 좁으면 한 줄 걸러 단다(0, -24, -48, -72).
        step = 2 if self.db_y(inner, -12) - self.db_y(inner, 0) < 16 else 1
        for db in SPECTRUM_DBS[:-1][::step]:
            y = round(self.db_y(inner, db))
            text = str(db)
            width, height = dc.GetTextExtent(text)
            dc.DrawText(text, inner.x + inner.width - width - 4, y + 1 if db == 0 else y - height)

    def draw_strip_ground(self, gc, regions):
        # 막대 자리마다 가운데에 낮은 점을 깔아 둔다. 소리가 없어도 띠가 비어 보이지 않게.
        gc.SetPen(wx.TRANSPARENT_PEN)
        # 바닥 점은 레벨 막대의 꺼진 칸과 같은 색 — 회색 점이 따로 놀지 않게(사용자: 최대한 깔끔하게).
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
        '''위상 상관(-1 … +1)과 좌우 균형(L 6 dB … R 6 dB). 레벨 막대와 같은 칸, 꺼진 칸은
        옅게, 가운데(0) 칸 위아래로 금 하나.'''
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
        '''PyMusicPlayer 는 폭 320 마다 막대를 한 벌(103 개)씩 더 촘촘히 나눈다(그쪽은 세 벌까지).
        막대는 늘 1 화소라, 여기서는 상한 없이 간격이 3 화소 안팎에 머물도록 벌 수를 고른다.'''
        width = self.get_bars_inner(self.regions['strip']).width
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
        '''막대는 1 화소, 간격은 늘 BAR_PITCH 화소로 띠 폭을 끝에서 끝까지 채운다. 반음 막대
        수와 자리 수가 다르면 값을 다시 고른다 — 자리가 많으면 이웃 막대 사이를 잇고(선형
        보간), 적으면 모이는 막대 중 큰 값을 남긴다. 예전에는 막대 수를 그대로 두고 간격을
        정수로 내려 띠 양옆이 비었다(사용자: 좌우로 꽉 채우되 뚱뚱하지 않게).'''
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
        # 가운데 줄에서 위아래로 같은 화소만큼 — 반올림이 위아래로 갈리면 막대 끝이 들쭉날쭉했다.
        middle = rect.y + rect.height // 2
        halves = numpy.maximum(floor, numpy.round(levels * rect.height * BAR_HEIGHT / 2)).astype(int)
        return [(int(rect.x + BAR_PITCH * index + offset), int(middle - half), BAR_WIDTH, int(half * 2))
                for index, half in enumerate(halves)]

    def get_spectrum_inner(self, rect):
        '''곡선 자리. 좌우·위아래 모두 LCD_PAD — 막대 띠와 끝이 맞는다.'''
        return wx.Rect(rect.x + LCD_PAD, rect.y + LCD_PAD, rect.width - LCD_PAD * 2,
                       rect.height - LCD_PAD * 2)

    def freq_x(self, inner, freq):
        return inner.x + inner.width * math.log(min(max(freq, 20.0), 20000.0) / 20.0) / \
            math.log(1000.0)

    def db_y(self, inner, db):
        ratio = (min(max(db, SPECTRUM_FLOOR), 0.0) - SPECTRUM_FLOOR) / -SPECTRUM_FLOOR
        return inner.y + inner.height * (1 - ratio)

    def on_paint(self, event):
        # 버퍼를 매 장 새로 만들면 그것만으로 한 장에 몇 ms 가 든다. 한 장을 쥐고 다시 쓴다.
        width, height = self.GetClientSize()
        if self.buffer is None or self.buffer.GetSize() != wx.Size(width, height):
            self.buffer = wx.Bitmap(max(1, width), max(1, height))
        dc = wx.BufferedPaintDC(self, self.buffer)
        key = (width, height, self.folded, self.pinned, self.flowing, self.left_margin,
               self.right_margin,
               tuple(self.parts.values()), getattr(self, 'hover_target', None))
        if self.background is None or self.background_key != key:
            self.background = self.build_background(width, height)
            self.background_key = key
        dc.DrawBitmap(self.background, 0, 0)
        if not self.regions:
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
        # 열마다 GDI 금을 그으면 3 ms 가 든다. 열마다 칠한 그림 한 장을 붙인다.
        height = inner.height
        middle = height / 2
        high, low, rms = self.wave
        rows = numpy.arange(height)[:, None]
        top = numpy.floor(middle - numpy.clip(high, -1, 1) * (middle - 1))[None, :]
        bottom = numpy.ceil(middle - numpy.clip(low, -1, 1) * (middle - 1))[None, :]
        reach = numpy.clip(rms, 0, 1) * (middle - 1)
        inside = (rows >= numpy.floor(middle - reach)[None, :]) & (rows <= numpy.ceil(middle + reach)[None, :])
        peak, body = self.get_wave_colour()
        image = numpy.zeros((height, inner.width, 4), dtype='uint8')
        image[(rows >= top) & (rows <= bottom)] = peak
        image[inside & (reach[None, :] > 0.5)] = body
        dc.DrawBitmap(wx.Bitmap.FromBufferRGBA(inner.width, height, image.tobytes()), inner.x, inner.y)

    def get_wave_colour(self):
        if getattr(self, 'wave_colour', None) is None:
            self.wave_colour = (list(mix(TRACE_BLUE, RACK['lcd'], 0.45).Get()[:3]) + [255],
                                list(wx.Colour(TRACE_BLUE).Get()[:3]) + [255])
        return self.wave_colour

    def fit_gram(self, height, width):
        '''창 크기가 바뀌어도 지난 기록을 버리지 않는다(사용자) — 가장 최근 쪽부터 오른쪽에 옮겨 담고,
        키가 달라졌으면 줄을 가까운 것으로 다시 고른다. 그릴 때도 부른다 — 다음 장까지 기다려
        크기가 다른 장을 건너뛰면 그 칸이 한 장씩 비어 깜빡였다(사용자).'''
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
        '''스펙트로그램과 같게 — 크기가 바뀌어도 최근 기록을 오른쪽에 옮겨 담는다.'''
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
            dc.DrawBitmap(wx.Bitmap.FromBuffer(width, height, self.gram.tobytes()), inner.x, inner.y)
        self.draw_gram_labels(dc, inner)

    def draw_status(self, dc):
        plate = self.regions['plate']
        right = self.regions['pin'].x - 8
        if self.capture.error:
            text = self.capture.error
        else:
            text = self.capture.device
        dc.SetFont(get_font(8))
        dc.SetTextForeground(wx.Colour(RACK['warn'] if self.capture.error else RACK['dim']))
        # 토글 단추들과 PIN 사이에 남는 만큼만 쓴다. 모자라면 비운다.
        limit = right - self.regions['chips_end'] - 16
        if limit < 40:
            return
        while text and dc.GetTextExtent(text)[0] > limit:
            text = text[:-2] + '…'
        top = plate.y + (FOLDED - dc.GetTextExtent(text or 'X')[1]) // 2
        dc.DrawText(text, right - dc.GetTextExtent(text)[0], top)

    def get_colour(self, db):
        if db >= -3:
            return METER_HIGH
        if db >= -9:
            return METER_MID
        return METER_BLUE

    def draw_levels(self, dc):
        '''L·R: RMS 까지 칸을 다 켜고, 그 위로 피크까지 옅게, 피크 홀드는 세로 한 줄.
        M·S·I: 라우드니스 값까지 제 색으로. 같은 색 칸끼리 모아 한 번에 그린다.'''
        regions = self.regions
        if 'level' not in regions:
            return
        rows = regions['rows']
        segments = regions['segments']
        momentary, short, integrated = self.loudness or (LOUDNESS_FLOOR,) * 3
        groups = {}

        def add(colour, rect):
            groups.setdefault(colour, []).append(rect)

        for channel, key in enumerate(('L', 'R')):
            row = rows[key]
            rms, peak, hold = self.rms[channel], self.peak[channel], self.hold[channel]
            for x, db, colour, half in segments:
                if db <= rms:
                    add(colour, (x, row.y, SEGMENT, row.height))
                elif db <= peak:
                    add(half, (x, row.y, SEGMENT, row.height))
                else:
                    break
            if hold > METER_FLOOR:
                add('#f2f4f6', (round(self.to_x(row, hold)) - 1, row.y - 2, 2, row.height + 4))
        dc.SetPen(wx.TRANSPARENT_PEN)
        for tone, rects in groups.items():
            dc.DrawRectangleList(rects, pens=wx.TRANSPARENT_PEN, brushes=get_brush(tone))
        for channel, clip in enumerate(regions['clips']):
            if self.clips[channel]:
                dc.SetBrush(get_brush(CLIP))
                dc.DrawRectangle(clip)

        values = {'Lpk': (self.hold[0], FLOOR), 'Rpk': (self.hold[1], FLOOR),
                  'Lrms': (self.rms[0], FLOOR), 'Rrms': (self.rms[1], FLOOR),
                  'M': (momentary, LOUDNESS_FLOOR), 'S': (short, LOUDNESS_FLOOR),
                  'I': (integrated, LOUDNESS_FLOOR)}
        dc.SetFont(get_mono(7.5))
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
            width, height = dc.GetTextExtent(text)
            dc.DrawText(text, box.x + box.width - width, box.y + (box.height - height) // 2)

    def format_db(self, value):
        return '-inf' if value <= FLOOR else '%.1f' % value

    def draw_spectrum(self, dc):
        '''채움은 위에서 아래로 옅어지는 그라데이션, 그 위에 밝은 선, 가는 피크 선.'''
        self.draw_bars(dc)
        if 'spectrum' not in self.regions:
            return
        # 곡선과 피크 선이 모두 바닥이면(무음) 그리지 않는다. 바닥에 한 줄이 남아 보였다.
        silent = (self.spectrum is not None and self.spectrum[1].max() <= SPECTRUM_FLOOR and
                  (self.spectrum_hold is None or
                   self.spectrum_hold[0].max() <= SPECTRUM_FLOOR))
        if self.spectrum is None or silent:
            self.draw_spectrum_labels(dc, self.get_spectrum_inner(self.regions['spectrum']))
            return
        rect = self.regions['spectrum']
        inner = self.get_spectrum_inner(rect)
        xs, values = self.spectrum
        ys = [self.db_y(inner, value) for value in values]
        bottom = inner.y + inner.height
        gc = wx.GraphicsContext.Create(dc)
        if gc is None:
            return
        gc.Clip(inner.x, inner.y, inner.width, inner.height)
        path = gc.CreatePath()
        path.MoveToPoint(xs[0], bottom)
        for x, y in zip(xs, ys):
            path.AddLineToPoint(x, y)
        path.AddLineToPoint(xs[-1], bottom)
        path.CloseSubpath()
        tone = wx.Colour(TRACE_BLUE)
        top = min(ys) if ys else inner.y
        gc.SetPen(wx.TRANSPARENT_PEN)
        gc.SetBrush(gc.CreateLinearGradientBrush(
            0, top, 0, bottom, wx.Colour(tone.Red(), tone.Green(), tone.Blue(), 150),
            wx.Colour(tone.Red(), tone.Green(), tone.Blue(), 12)))
        gc.FillPath(path)
        line = gc.CreatePath()
        line.MoveToPoint(xs[0], ys[0])
        for x, y in zip(xs[1:], ys[1:]):
            line.AddLineToPoint(x, y)
        gc.SetPen(gc.CreatePen(wx.GraphicsPenInfo(wx.Colour(TRACE_BLUE)).Width(1.4).Join(wx.JOIN_ROUND)))
        gc.SetBrush(wx.TRANSPARENT_BRUSH)
        gc.StrokePath(line)
        hold = self.spectrum_hold[0] if self.spectrum_hold is not None else None
        if hold is not None and len(hold) == len(xs):
            peaks = gc.CreatePath()
            peaks.MoveToPoint(xs[0], self.db_y(inner, hold[0]))
            for x, value in zip(xs[1:], hold[1:]):
                peaks.AddLineToPoint(x, self.db_y(inner, value))
            gc.SetPen(gc.CreatePen(wx.GraphicsPenInfo(wx.Colour(200, 204, 210, 110)).Width(1)))
            gc.StrokePath(peaks)
        gc.ResetClip()
        del gc
        self.draw_spectrum_labels(dc, inner)
        self.draw_hover(dc, inner, xs, values)

    def draw_hover(self, dc, inner, xs, values):
        '''마우스 자리에 세로 금 하나와 작은 읽기 칸. 칸은 금 오른쪽에, 끝에 닿으면 왼쪽에.'''
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
            dc.DrawBitmap(self.scope, scope.x, scope.y)
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
            # 가운데 칸에서 값 쪽으로 칸을 켜고, 끝 칸은 밝게(예전 표시 자리).
            xs = regions['phase_segments']
            centre = regions['phase_middle']
            reach = round((ratio - 0.5) * 2 * centre)
            end = min(max(centre + reach, 0), len(xs) - 1)
            low, high = min(centre, end), max(centre, end)
            dc.DrawRectangleList([(x, bar.y, SEGMENT, bar.height) for x in xs[low:high + 1]],
                                 pens=wx.TRANSPARENT_PEN, brushes=get_brush(tone))
            bright = mix(tone, '#ffffff', 0.45).GetAsString(wx.C2S_HTML_SYNTAX)
            dc.SetBrush(get_brush(bright))
            dc.DrawRectangle(xs[end], bar.y - 1, SEGMENT, bar.height + 2)
            box = regions['phase_boxes'][key]
            dc.SetTextForeground(wx.Colour(RACK['text']))
            width, height = dc.GetTextExtent(value)
            dc.DrawText(value, box.x + box.width - width, box.y + (box.height - height) // 2)

    # ------------------------------------------------------------ 한 장

    def tick(self):
        # 창을 닫은 뒤에도 이미 줄 서 있던 부탁이 한 번 더 올 수 있다. 지워진 창은 거짓이다.
        if not self:
            return
        if self.pacer is not None:
            self.pacer.pending = False
        if not self.is_running() or not self.regions or not self.IsShownOnScreen():
            return
        # 핀을 뺀 채 랙을 굴려 판이 위로 다 올라갔으면 그리지 않는다.
        if self.GetPosition().y + self.GetSize().height <= 0:
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
        if now - self.loudness_at > LOUDNESS_EVERY or self.loudness is None:
            self.loudness_at = now
            self.loudness = self.capture.take_loudness()
        self.frame_power = None
        self.update_spectrum(recent, elapsed)
        self.update_scope(recent[-SCOPE_SAMPLES:])
        self.update_wave(recent, elapsed)
        self.update_gram(recent)
        # 소리가 없고 모든 계기가 바닥에 닿았으면 같은 그림을 다시 그리지 않는다.
        quiet = (max(peaks) == 0.0 and max(self.peak) <= FLOOR and max(self.hold) <= FLOOR and
                 (self.spectrum is None or self.spectrum[1].max() <= SPECTRUM_FLOOR) and
                 # 피크 선이 바닥까지 내려온 뒤에야 멈춘다. 곡선만 보면 피크 선이 남은 채 굳었다.
                 (self.spectrum_hold is None or self.spectrum_hold[0].max() <= SPECTRUM_FLOOR) and
                 (self.bars is None or self.bars.max() < 1e-3) and
                 abs(self.correlation) < 0.005 and abs(self.balance) < 0.05 and
                 # 스펙트로그램은 지난 소리가 왼쪽 끝으로 다 밀려 나갈 때까지 흐른다.
                 (self.gram is None or self.gram_dark >= self.gram.shape[1]) and
                 (self.wave is None or self.wave_dark >= self.wave.shape[1]))
        if quiet and self.drawn_quiet:
            return
        self.drawn_quiet = quiet
        # 판 머리와 레일은 그대로다. 움직이는 칸만 다시 그리게 해 화면으로 옮기는 양을 줄인다.
        plate = self.regions['plate']
        self.RefreshRect(wx.Rect(plate.x, plate.y + FOLDED, plate.width,
                                 self.GetClientSize().height - FOLDED), False)

    def draw_bars(self, dc):
        if self.bars is None or 'strip' not in self.regions:
            return
        rect = self.get_bars_inner(self.regions['strip'])
        levels = numpy.minimum(self.bars, 1.0 / BAR_HEIGHT)
        dc.SetClippingRegion(rect)
        # 0 인 자리는 그리지 않아 바닥 점이 그대로 보인다(최소 2 화소로 칠하면 무음 자리도 파랗게 찍혔다).
        rects = [box for box in self.get_bar_rects(rect, levels, floor=0) if box[3] > 0]
        if rects:
            dc.DrawRectangleList(rects, pens=wx.TRANSPARENT_PEN, brushes=get_brush(BAR_COLOUR))
        dc.DestroyClippingRegion()

    def update_bars(self, recent, elapsed):
        '''audio.get_stream_spectrum_vectorscope 의 셈을 옮긴 것. 그쪽처럼 왼쪽 채널만 쓰고,
        16 비트 정수 표본을 받던 셈이라 같은 크기로 늘려 넣는다.'''
        scale = self.get_bar_scale()
        bins = self.get_bar_bins()
        left = recent[-BAR_FRAME:, 0].astype('float64')
        raw = numpy.abs(numpy.fft.fft(left, BAR_POINTS))[1:BAR_POINTS // 2]
        self.follow_autogain(raw, elapsed)
        # 원본은 벌 수만큼 키우되 세 벌이 끝이다. 벌 수를 더 늘려도 크기는 거기서 멈춘다.
        amplify = (self.autogain * (1.0 / 0.4) * 2 * (RATE / 44100.0) * 1.25 *
                   math.sqrt(min(scale, 3)))
        spectrum = raw * 32768.0 * amplify / BAR_POINTS / 8192
        levels = numpy.empty(len(bins) - 1)
        for index, value in enumerate(bins[:-1]):
            low = max(0, int(value) - BAR_REACH)
            peak = spectrum[low:max(int(bins[index + 1]) + 1, int(value) + BAR_REACH + 1)].max()
            level = peak * math.log(1 + value, 2) * (value ** 0.25)
            levels[index] = (level ** (1.4 * ((2 + index) / (1 + index)))) * 1.5
        self.bars = levels

    def follow_autogain(self, raw, elapsed):
        '''mfeats 의 필터를 거친 RMS 를 FFT 에서 바로 낸다(파스발 — 덧붙인 0 은 에너지가 없다).'''
        energy = 2.0 * float((raw ** 2 * AUTOGAIN_WEIGHTS).sum()) / BAR_POINTS / BAR_FRAME
        rms = math.sqrt(energy) * 3
        if rms < 1e-4:
            return
        low, high = AUTOGAIN_RANGE
        target = min(high, max(low, 0.14 / rms))
        self.autogain += (target - self.autogain) * min(1.0, elapsed / AUTOGAIN_FOLLOW)

    def update_spectrum(self, recent, elapsed):
        '''8192 점 FFT 를 칸마다 파워로 평균해(최대값 아님) 기울기를 얹고, 시간으로 고르게
        한 곡선과 1 초 머무는 피크 선을 함께 둔다.'''
        if 'strip' in self.regions:
            self.update_bars(recent, elapsed)
        if 'spectrum' not in self.regions:
            return
        inner = self.get_spectrum_inner(self.regions['spectrum'])
        if inner.width < 8:
            return
        power = self.get_frame_power(recent)
        freqs = numpy.fft.rfftfreq(FFT_SIZE, 1.0 / RATE)
        columns = max(32, inner.width // 2)
        edges = 20.0 * numpy.power(1000.0, numpy.linspace(0, 1, columns + 1))
        centres = numpy.sqrt(edges[:-1] * edges[1:])
        starts = numpy.minimum(numpy.searchsorted(freqs, edges[:-1]), len(power) - 1)
        stops = numpy.maximum(numpy.searchsorted(freqs, edges[1:]), starts + 1)
        sums = numpy.add.reduceat(power, starts)
        counts = numpy.diff(numpy.append(starts, len(power)))
        values = sums / numpy.maximum(counts, 1)
        # 저역은 칸이 FFT 칸보다 좁다. 칸 가운데 주파수에서 이웃 FFT 칸 둘을 이어 읽는다.
        narrow = (stops - starts) <= 1
        if narrow.any():
            values[narrow] = numpy.interp(centres[narrow], freqs, power)
        values = 10 * numpy.log10(numpy.maximum(values, 1e-12))
        values += SPECTRUM_TILT * numpy.log2(centres / 1000.0)
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
        xs = numpy.array([self.freq_x(inner, freq) for freq in centres])
        self.spectrum = (xs, values)

    def get_frame_power(self, recent):
        '''이 장의 8192 점 파워. 분석기와 스펙트로그램이 함께 쓴다.'''
        if self.frame_power is None:
            mono = recent.mean(axis=1) * self.window
            self.frame_power = (numpy.abs(numpy.fft.rfft(mono)) * (4.0 / FFT_SIZE)) ** 2
        return self.frame_power

    def update_wave(self, recent, elapsed):
        '''지난 장 이후 들어온 만큼(약 1/30 초)의 가장 높은·낮은 값과 RMS 를 한 열로. 스펙트로그램과
        같은 장에서 같이 한 칸 밀어 두 칸의 같은 세로 줄이 같은 순간이다.'''
        if 'oscilloscope' not in self.regions:
            return
        width = self.get_wave_inner(self.regions['oscilloscope']).width
        if width < 4:
            return
        self.fit_wave(width)
        count = min(len(recent), max(1, int(round(elapsed * RATE))))
        mono = recent[-count:].mean(axis=1)
        column = (float(mono.max()), float(mono.min()), float(numpy.sqrt((mono ** 2).mean())))
        self.wave[:, :-1] = self.wave[:, 1:]
        self.wave[:, -1] = column
        self.wave_dark = self.wave_dark + 1 if max(abs(column[0]), abs(column[1])) < 1e-4 else 0

    def get_gram_colours(self):
        if getattr(self, 'gram_colours', None) is None:
            stops = [(at, numpy.array(wx.Colour(tone).Get()[:3], dtype='float64'))
                     for at, tone in GRAM_STOPS]
            table = numpy.zeros((256, 3), dtype='uint8')
            for index in range(256):
                ratio = index / 255
                for (a, ca), (b, cb) in zip(stops, stops[1:]):
                    if ratio <= b:
                        table[index] = ca + (cb - ca) * ((ratio - a) / max(b - a, 1e-9))
                        break
            self.gram_colours = table
        return self.gram_colours

    def update_gram(self, recent):
        if 'spectrogram' not in self.regions:
            return
        inner = self.get_spectrum_inner(self.regions['spectrogram'])
        height, width = inner.height, inner.width
        if height < 4 or width < 4:
            return
        colours = self.get_gram_colours()
        self.fit_gram(height, width)
        if self.gram_rows is None or self.gram_rows[0] != height:
            # 줄마다 주파수 칸(위가 높은 소리). 분석기처럼 칸 평균, 좁은 저역은 이어 읽기.
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
        self.gram_dark = self.gram_dark + 1 if index.max() == 0 else 0

    def update_scope(self, block):
        left, right = block[:, 0], block[:, 1]
        if 'scope' in self.regions:
            self.update_glow(self.regions['scope'], left, right)
        # 소리가 없으면 둘 다 가운데(0)로 돌아간다. 마지막 값에 멈춰 있으면 소리가 나는
        # 것처럼 보인다(사용자).
        denominator = float(numpy.sqrt((left ** 2).sum() * (right ** 2).sum()))
        value = float((left * right).sum()) / denominator if denominator > 1e-9 else 0.0
        self.correlation += (value - self.correlation) * 0.25
        # 좌우 균형: 두 채널 RMS 의 dB 차.
        value = self.rms[0] - self.rms[1] if min(self.rms) > FLOOR else 0.0
        self.balance += (value - self.balance) * 0.15

    def update_glow(self, scope, left, right):
        energy = float(numpy.sqrt((left ** 2 + right ** 2).mean()))
        # 점들이 늘 화면을 알맞게 채우도록 이득을 천천히 따라 맞춘다.
        target = min(8.0, 0.35 / max(energy, 1e-4))
        self.scope_gain += (target - self.scope_gain) * 0.15
        radius = self.get_scope_radius(scope)
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

    def paint_glow(self, glow):
        '''밝기 판을 LCD 바탕에서 점 색까지 섞어 비트맵으로. 격자는 그 아래 바탕에 있어
        점이 없는 자리만 비쳐 보이게 0 인 칸은 바탕과 같은 색이 아니라 투명으로 둔다.'''
        height, width = glow.shape
        base = numpy.array(wx.Colour(RACK['lcd']).Get()[:3], dtype='float32')
        # 점 색은 막대 무리의 METER_BLUE 쪽으로(사용자: 벡터스코프만 짙었다), 점이 몰려 하얗게 뜨지 않게
        # 원래 파랑을 35 % 남긴다(사용자: 조금 더 어둡게).
        dot = numpy.array(wx.Colour(TRACE_BLUE).Get()[:3], dtype='float32')
        level = glow[..., None]
        rgb = (base + (dot - base) * level).astype('uint8')
        alpha = (numpy.minimum(1.0, glow * 4) * 255).astype('uint8')
        return wx.Bitmap.FromBufferRGBA(width, height,
                                        numpy.dstack([rgb, alpha[..., None]]).tobytes())

    # ------------------------------------------------------------ 마우스

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
            self.clips = [False, False]
            self.hold = [FLOOR, FLOOR]
            self.Refresh(False)
        elif target == 'integrated':
            self.capture.reset_integrated()
            self.loudness = None

    def on_wheel(self, event):
        '''핀을 뺐을 때는 이 판도 랙의 한 칸이다. 휠은 랙을 굴린다.'''
        if (not self.pinned or self.flowing) and self.on_wheel_rack is not None:
            self.on_wheel_rack(event)

    on_wheel_rack = None

    def on_leave(self, event):
        self.set_hover(None)
        self.set_hover_target(None)
        event.Skip()

    def set_hover_target(self, target):
        '''머리 띠 단추 위에 손이 오가면 띠만 다시 그린다.'''
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
        if 'spectrum' in self.regions:
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
