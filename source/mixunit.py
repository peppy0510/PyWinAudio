# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com

랙에 붙박인 프로그램별 볼륨 장치. 맨 왼쪽 채널이 출력 장치 전체, 그 오른쪽으로 소리를
낸 프로그램들. 폭이 모자라면 다음 줄로 접어 내린다.

랙의 다른 손잡이와 같이 휠로는 바뀌지 않는다 — 페이더는 끌어서만 움직인다.
빼거나 옮길 수 없고, 접기만 된다.
'''


import math
import wx

from mixer import Mixer
from rackui import FACES
from rackui import HEADER_BAND
from rackui import RACK
from rackui import Button
from rackui import Control
from rackui import IconButton
from rackui import draw_faceplate
from rackui import draw_text
from rackui import draw_title
from rackui import fill_rect
from rackui import fit_text
from rackui import get_pen
from rackui import mix
from rackui import set_font
from units import EAR
from units import FOLD
from units import FOLDED
from units import INSET
from units import TIGHT_PAD


COLUMN = 64
# 채널 사이는 1 화소 금(사용자: 세로 구분선도 가늘게). 가로 금과 같은 색.
COLUMN_GAP = 1
COLUMN_HEIGHT = 222
# 가르는 금과 위아래 글씨·손잡이 사이(실측해 맞춘 값).
RULE_GAP = 8
# 손잡이 길 아래 끝에서 칸 아래 끝까지. 그 사이에 가르는 금, 그 아래 볼륨 숫자와 M.
FOOT = 45
HEADER = HEADER_BAND + 1 + TIGHT_PAD
ICON = 16
FLOOR = -60.0
METER_CURVE = 0.6

# 믹서 미터는 검은 바탕 위 빛나는 청록 칸. 넘칠 때만 호박색·주황.
LOW = '#2fd2e8'
MID = '#ffb04d'
HIGH = '#ff7a33'
SCALE_TEXT = '#3fb6c6'
# 페이더는 콘솔처럼 dB 로 움직인다. 세션 볼륨은 선형 배율이라 20·log10 이 곧 dB 다.
TAPER_FLOOR = -60.0
FADER_MARKS = (0, -6, -12, -20, -30, -40, -60)
METER_GROUND = RACK['lcd']
# 출력 레벨미터와 같은 칸 나뉜 막대. 칸 3 화소 + 틈 1 화소, 꺼진 칸은 옅게.
# 레벨은 가는 칸 막대. 칸 2 화소 + 틈 1 화소, 막대 폭 4.
DOT = 6
SEG = 2
SEG_GAP = 1
SEGMENT_OFF = 0.84
CAP_HEIGHT = 10
MUTE_SIZE = 20
# 이름 줄 끝과 손잡이 맨 위 사이. 가운데에 가르는 금이 서고 금 위아래가 10 씩 남는다.
NAME_GAP = 19
# 레벨 다듬기. 지난 0.3 초 안의 가장 큰 값을 겉봉으로 잡고, 오를 때 40 ms·내릴 때 350 ms
# 시정수로 따라간다. 0.6 dB 안쪽의 흔들림은 칸을 바꾸지 않는다.
WINDOW = 0.3
ATTACK = 0.04
RELEASE = 0.35
DEADBAND = 0.6


class ChannelFader(Control):
    '''세로 페이더. 손잡이를 잡으면 그 자리에서 끌고, 길 위 다른 곳을 누르면 그리로 옮긴다.'''

    cursor = wx.CURSOR_SIZENS

    # 바꾼 볼륨을 곧장 보이게 다시 그려 달라는 자리. 장치가 채운다.
    on_move = staticmethod(lambda: None)

    def __init__(self, channel, accent):
        super().__init__()
        self.channel = channel
        self.accent = accent
        self.origin = None

    @staticmethod
    def to_ratio(volume):
        '''볼륨(선형 배율) → 페이더 자리(0~1). dB 를 제곱근 곡선으로 펴서 위쪽이 넓다.'''
        if volume <= 1e-6:
            return 0.0
        db = max(TAPER_FLOOR, 20 * math.log10(min(volume, 1.0)))
        return 1.0 - math.sqrt(db / TAPER_FLOOR)

    @staticmethod
    def from_ratio(ratio):
        ratio = min(max(ratio, 0.0), 1.0)
        if ratio <= 0.0:
            return 0.0
        return 10 ** (TAPER_FLOOR * (1.0 - ratio) ** 2 / 20)

    def to_y(self, volume):
        rect = self.rect
        return rect.y + rect.height * (1.0 - self.to_ratio(volume))

    def from_y(self, y):
        rect = self.rect
        return self.from_ratio(1.0 - (y - rect.y) / max(1, rect.height))

    def contains(self, point):
        return wx.Rect(self.rect).Inflate(6, 8).Contains(point)

    def on_down(self, point, shift):
        super().on_down(point, shift)
        if abs(point.y - self.to_y(self.channel.get_volume())) > 8:
            self.channel.set_volume(self.from_y(point.y))
        self.origin = (point.y, self.to_ratio(self.channel.get_volume()), shift)
        self.on_move()

    def on_drag(self, point, shift):
        if self.origin is None:
            return
        top, ratio, fine = self.origin
        if shift != fine:
            self.origin = (point.y, self.to_ratio(self.channel.get_volume()), shift)
            return
        span = self.rect.height * (10 if shift else 1)
        self.channel.set_volume(self.from_ratio(ratio + (top - point.y) / max(1, span)))
        # 볼륨은 세션에 바로 들어가지만 화면은 누가 다시 그려 주지 않으면 손잡이가 놓을
        # 때까지 제자리에 서 있다(사용자: 움직이기 힘들다).
        self.on_move()

    def on_up(self, point):
        self.pressed = False
        self.origin = None

    def draw(self, gc, accent):
        '''가는 길, 왼쪽에 dB 눈금 숫자(청록), 밝은 회색 납작한 손잡이.'''
        rect = self.rect
        cx = rect.x + rect.width / 2
        volume = self.channel.get_volume()
        fill_rect(gc, RACK['track'], cx - 1, rect.y, 2, rect.height, 1)
        y = self.to_y(volume)
        fill_rect(gc, self.accent, cx - 1, y, 2, rect.y + rect.height - y, 1)
        for db in FADER_MARKS:
            ty = round(self.to_y(10 ** (db / 20)))
            fill_rect(gc, RACK['faint'], cx - 6, ty, 4, 1)
            fill_rect(gc, RACK['faint'], cx + 2, ty, 4, 1)
            draw_text(gc, str(abs(db)), rect.x - 2, ty - 5, 6, SCALE_TEXT, align='right')
        lit = self.hovered or self.pressed
        cap = wx.Rect(round(rect.x + 3), round(y - CAP_HEIGHT / 2), rect.width - 6, CAP_HEIGHT)
        gc.SetPen(wx.TRANSPARENT_PEN)
        gc.SetBrush(wx.Brush(wx.Colour('#e6e7e9' if lit else '#c4c7cc')))
        gc.DrawRoundedRectangle(cap.x, cap.y, cap.width, cap.height, 2)
        fill_rect(gc, '#2a2d32', cap.x + 3, y - 0.5, cap.width - 6, 1)


class Column:

    def __init__(self, unit, channel, master):
        self.channel = channel
        self.master = master
        accent = FACES['master'][1] if master else LOW
        self.fader = ChannelFader(channel, mix(accent, '#000000', 0.25).GetAsString(
            wx.C2S_HTML_SYNTAX))
        self.fader.on_move = unit.repaint
        self.mute = Button('M', self.toggle_mute, active=lambda: self.channel.get_mute())
        self.mute.tip = 'Mute ' + channel.name
        self.rect = wx.Rect()
        self.meter = wx.Rect()

    def adopt(self, channel):
        '''목록을 다시 읽으면 같은 프로그램도 새 채널 객체로 온다. 칸·페이더·자리는 그대로
        두고 채널만 바꿔 끼운다 — 칸을 새로 만들면 다음 전체 그리기까지 레벨 칸 자리가 비어
        엉뚱한 곳이 번쩍이고, 끌던 페이더도 놓친다.'''
        self.channel = channel
        self.fader.channel = channel

    def toggle_mute(self):
        self.channel.set_mute(not self.channel.get_mute())

    def layout(self, x, y):
        '''NI 식 채널: 위에 작은 아이콘과 이름, 가운데 페이더와 바로 옆 가는 미터, 아래에
        볼륨 숫자와 M(음소거).'''
        self.rect = wx.Rect(x, y, COLUMN, COLUMN_HEIGHT)
        # 이름 줄(아이콘 아래 y+29, 글씨 11)과 손잡이 맨 위 사이를 NAME_GAP 만큼 띄운다.
        top = y + 40 + NAME_GAP + CAP_HEIGHT // 2
        bottom = y + COLUMN_HEIGHT - FOOT - CAP_HEIGHT // 2
        # 왼쪽부터 미터, dB 숫자, 페이더.
        self.meter = wx.Rect(x + 9, top - CAP_HEIGHT // 2, DOT, bottom - top + CAP_HEIGHT)
        self.fader.rect = wx.Rect(x + 34, top, 22, bottom - top)
        # M 단추는 페이더 길(손잡이) 가운데에 맞춘다(사용자).
        # 길은 2 화소라 가운데가 반 칸에 놓인다. 단추 테두리도 짝수 폭(20)으로 보이게 칸을 21 로
        # 잡아 두 가운데를 정확히 겹친다(실측).
        centre = self.fader.rect.x + self.fader.rect.width // 2
        self.mute.rect = wx.Rect(centre - MUTE_SIZE // 2 - 1, y + COLUMN_HEIGHT - 8 - MUTE_SIZE,
                                 MUTE_SIZE + 1, MUTE_SIZE)
        self.value = (x + 8, y + COLUMN_HEIGHT - 8 - MUTE_SIZE // 2)

class MixerUnit:

    def __init__(self, rack, data):
        self.rack = rack
        self.data = data
        self.mixer = Mixer()
        self.columns = []
        self.levels = {}
        self.recent = {}
        self.smooth = {}
        self.icons = {}
        self.rect = wx.Rect()
        self.face, self.accent = FACES['master']
        self.fold = IconButton('down', self.toggle_fold, tip='Fold')
        self.height = FOLDED
        self.segments = None

    @property
    def folded(self):
        return bool(self.data.get('folded'))

    def repaint(self):
        '''믹서 판만 다시 그리게 한다. 랙의 다른 장치는 건드리지 않는다.'''
        rect = self.rect
        self.rack.RefreshRect(wx.Rect(rect.x, rect.y - self.rack.offset, rect.width,
                                      rect.height), False)

    def toggle_fold(self):
        self.data['folded'] = not self.folded
        if not self.folded:
            self.refresh()
        self.rack.on_unit_change(None)

    # ------------------------------------------------------------ 채널

    def refresh(self):
        '''세션을 다시 읽는다. 채널이 들고 나면 참 — 랙 자리를 다시 잡아야 한다.'''
        before = [(column.channel.key, column.channel.name, column.channel.active)
                  for column in self.columns]
        self.mixer.refresh()
        channels = ([self.mixer.master] if self.mixer.master is not None else []) + \
            list(self.mixer.channels)
        kept = {column.channel.key: column for column in self.columns}
        columns = []
        for index, channel in enumerate(channels):
            column = kept.get(channel.key)
            if column is None or column.master != (index == 0):
                column = Column(self, channel, index == 0)
            else:
                column.adopt(channel)
            columns.append(column)
        self.columns = columns
        after = [(column.channel.key, column.channel.name, column.channel.active)
                 for column in self.columns]
        return before != after

    def update_levels(self, elapsed, fall):
        '''세션 미터는 호출 사이의 최대가 아니라 아주 짧은 구간의 순간 피크를 준다. 30 Hz 로
        띄엄띄엄 읽으면 장마다 들쭉날쭉하다. 오르내림을 바로 따르면 맨 위 칸이 쉬지 않고
        떨린다(사용자 지적 두 번). 그래서 짧은 창의 최대로 겉봉을 잡아 고르게 따라가고,
        아주 작은 차이는 무시한다. fall 은 옛 부름을 받아 주기만 한다.'''
        changed = set()
        now = self.clock = getattr(self, 'clock', 0.0) + elapsed
        attack = 1.0 - math.exp(-elapsed / ATTACK)
        release = 1.0 - math.exp(-elapsed / RELEASE)
        for column in self.columns:
            key = column.channel.key
            peak = column.channel.get_peak()
            value = 20 * math.log10(peak) if peak > 1e-6 else FLOOR
            recent = self.recent.setdefault(key, [])
            recent.append((now, value))
            while recent and now - recent[0][0] > WINDOW:
                recent.pop(0)
            target = max(item[1] for item in recent)
            smooth = self.smooth.get(key, FLOOR)
            smooth += (target - smooth) * (attack if target > smooth else release)
            smooth = max(smooth, FLOOR)
            self.smooth[key] = smooth
            shown = self.levels.get(key, FLOOR)
            if abs(smooth - shown) > DEADBAND or smooth <= FLOOR + DEADBAND:
                self.levels[key] = smooth
            if self.get_lit(column.meter, self.levels.get(key, FLOOR)) != \
                    self.get_lit(column.meter, shown):
                changed.add(key)
        return changed

    def get_lit(self, meter, db):
        '''켜진 칸 수. 칸이 그대로면 다시 칠하지 않는다.'''
        return sum(1 for top, edge, lit, dark in self.get_segments(meter) if db >= edge)

    # ------------------------------------------------------------ 자리

    def get_per_row(self, width):
        inner = width - TIGHT_PAD * 2
        return max(1, (inner + COLUMN_GAP) // (COLUMN + COLUMN_GAP))

    def get_height(self, width):
        if self.folded:
            return FOLDED
        count = max(1, len(self.columns))
        rows = math.ceil(count / self.get_per_row(width))
        return HEADER + rows * (COLUMN_HEIGHT + COLUMN_GAP) - COLUMN_GAP + TIGHT_PAD

    def get_controls(self):
        controls = [self.fold]
        if not self.folded:
            for column in self.columns:
                controls.extend((column.fader, column.mute))
        return controls

    def layout(self, gc, rect):
        self.rect = rect
        left = rect.x + EAR + INSET
        self.fold.glyph = 'right' if self.folded else 'down'
        self.fold.tip = 'Unfold' if self.folded else 'Fold'
        self.fold.rect = wx.Rect(left - 4, rect.y + (FOLDED - FOLD) // 2, FOLD, FOLD)
        if self.folded:
            return
        per_row = self.get_per_row(rect.width)
        for index, column in enumerate(self.columns):
            row, place = divmod(index, per_row)
            column.layout(rect.x + TIGHT_PAD + place * (COLUMN + COLUMN_GAP),
                          rect.y + HEADER + row * (COLUMN_HEIGHT + COLUMN_GAP))

    # ------------------------------------------------------------ 그림

    def get_icon(self, path):
        if path in self.icons:
            return self.icons[path]
        bitmap = None
        # wx.Bitmap(icon) 은 4.3 에서 XPM 목록 생성자로 읽혀 실패한다. .ico 는 가장 큰 판을
        # 그림으로 읽어 줄이고, exe 는 아이콘을 비트맵으로 옮겨 담는다.
        try:
            image = None
            if path.lower().endswith('.ico'):
                image = wx.Image(path, wx.BITMAP_TYPE_ICO)
            else:
                icon = wx.Icon(wx.IconLocation(path, 0))
                if icon.IsOk():
                    copy = wx.Bitmap()
                    copy.CopyFromIcon(icon)
                    image = copy.ConvertToImage()
            if image is not None and image.IsOk():
                bitmap = image.Scale(ICON, ICON, wx.IMAGE_QUALITY_HIGH).ConvertToBitmap()
        except Exception:
            bitmap = None
        self.icons[path] = bitmap
        return bitmap

    def get_subtitle(self):
        if self.mixer.error:
            return self.mixer.error
        count = len(self.mixer.channels)
        return '%d program%s' % (count, '' if count == 1 else 's')

    def draw(self, gc):
        rect = self.rect
        draw_faceplate(gc, rect.x, rect.y, rect.width, rect.height, self.face, EAR, self.accent)
        # 불이 없는 판이라 그 자리에 스피커 표시를 둔다(사용자: 이름 왼쪽이 비어 보인다).
        # 제목은 다른 장치들과 같은 x 에 선다.
        # 표시는 -9 … +11 폭이라 가운데를 한 칸 왼쪽으로, 키는 불 표시(11)와 같게 줄인다.
        # 누르는 단추가 아니라 회색(master=False). 장치 색은 누를 수 있는 것에만 쓴다.
        self.draw_speaker(gc, rect.x + EAR + INSET + FOLD + 7 - 0.6, rect.y + FOLDED / 2, False, 0.62)
        left = rect.x + EAR + INSET + FOLD + 22
        draw_title(gc, left, rect.y, 'Mixer', self.get_subtitle(),
                   RACK['warn'] if self.mixer.error else RACK['dim'],
                   rect.x + rect.width - EAR - INSET - left)
        self.fold.draw(gc, self.accent)
        if self.folded:
            return
        for index, column in enumerate(self.columns):
            self.draw_column(gc, column)
            following = self.columns[index + 1] if index + 1 < len(self.columns) else None
            if following is not None and following.rect.y == column.rect.y:
                rect = column.rect
                fill_rect(gc, RACK['line'], rect.x + rect.width, rect.y, COLUMN_GAP, rect.height)

    def draw_column(self, gc, column):
        rect, channel = column.rect, column.channel
        fill_rect(gc, RACK['band'], rect.x, rect.y, rect.width, rect.height)
        if column.master:
            fill_rect(gc, self.accent, rect.x + 6, rect.y, rect.width - 12, 2, 1)
        # 이름 줄: 작은 아이콘을 왼쪽에, 이름은 남은 폭에 맞춰 자른다. 두 번째 줄은 쓰지 않는다.
        icon = self.get_icon(channel.icon) if channel.icon else None
        x, y = rect.x + 7, rect.y + 9
        if icon is not None:
            gc.DrawBitmap(icon, x, y, ICON, ICON)
        else:
            self.draw_speaker(gc, x + ICON / 2, y + ICON / 2, column.master, 0.75)
        colour = RACK['text'] if channel.active else RACK['dim']
        set_font(gc, 7.5, colour, bold=True)
        draw_text(gc, fit_text(gc, channel.name, rect.width - 14), rect.x + 7, y + ICON + 4,
                  7.5, colour, bold=True)
        # 이름 머리와 아래 미터·페이더를 가르는 금. 이름 줄 끝(y+40)과 미터 맨 위(y+60) 가운데.
        fill_rect(gc, RACK['line'], rect.x, rect.y + 41 + RULE_GAP + 1, rect.width, 1)
        # 아래도 같은 금: M 단추 위 끝에서 RULE_GAP 위. 그 위 손잡이 끝까지도 RULE_GAP.
        foot = rect.y + rect.height - 8 - MUTE_SIZE - RULE_GAP - 1
        fill_rect(gc, RACK['line'], rect.x, foot, rect.width, 1)

        meter = column.meter
        fill_rect(gc, METER_GROUND, meter.x, meter.y, meter.width, meter.height)
        db = self.levels.get(channel.key, FLOOR)
        for top, edge, lit, dark in self.get_segments(meter):
            fill_rect(gc, lit if db >= edge else dark, meter.x, meter.y + top, meter.width, SEG)
        column.fader.draw(gc, self.accent)

        muted = channel.get_mute()
        volume = channel.get_volume()
        value = '-inf' if volume <= 1e-6 else '%.1f' % (20 * math.log10(min(volume, 1.0)))
        x, middle = column.value
        # 볼륨 숫자는 M 단추에 붙지 않게 작게(사용자). '-12.4' 가 단추 앞 4 화소에서 끝난다.
        draw_text(gc, value, x, middle - 5, 7, RACK['warn'] if muted else RACK['text'], bold=True)
        column.mute.draw(gc, RACK['warn'])

    def get_segments(self, meter):
        '''아래에서 위로 칸마다 (meter 안의 y, 그 칸이 켜지는 dB, 켜진 색, 꺼진 색).
        채널마다 막대 키가 같아 한 번 셈한 것을 함께 쓴다.'''
        if self.segments is not None and self.segments[0] == meter.height:
            return self.segments[1]
        pitch = SEG + SEG_GAP
        count = max(1, (meter.height + SEG_GAP) // pitch)
        bottom = meter.height
        segments = []
        for index in range(count):
            top = bottom - SEG - index * pitch
            ratio = (index + 1) / count
            edge = FLOOR * (1.0 - ratio) ** (1.0 / METER_CURVE)
            middle = FLOOR * (1.0 - (index + 0.5) / count) ** (1.0 / METER_CURVE)
            lit = HIGH if middle >= -3 else MID if middle >= -12 else LOW
            dark = mix(lit, RACK['lcd'], SEGMENT_OFF).GetAsString(wx.C2S_HTML_SYNTAX)
            segments.append((top, edge, lit, dark))
        self.segments = (meter.height, segments)
        return segments

    def paint_levels(self, dc, offset, box=None):
        '''레벨 칸만 다시 칠한다. 판·글씨·페이더는 그대로 둔다. 화면에 바로 바탕부터 칠하면
        한 장마다 빈 막대가 잠깐 비쳐 떨려 보였다. 막대마다 따로 한 장에 다 그린 뒤 한 번에
        옮긴다. 그림은 draw_column 의 칸과 같다.'''
        for column in self.columns:
            meter = column.meter
            target = wx.Rect(meter.x, meter.y - offset, meter.width, meter.height)
            if box is not None and not box.Intersects(target):
                continue
            bitmap = wx.Bitmap(max(1, meter.width), max(1, meter.height), 24)
            memory = wx.MemoryDC(bitmap)
            memory.SetBackground(wx.Brush(wx.Colour(METER_GROUND)))
            memory.Clear()
            db = self.levels.get(column.channel.key, FLOOR)
            groups = {}
            for top, edge, lit, dark in self.get_segments(meter):
                groups.setdefault(lit if db >= edge else dark, []).append(
                    (0, top, meter.width, SEG))
            for colour, rects in groups.items():
                memory.DrawRectangleList(rects, pens=wx.TRANSPARENT_PEN,
                                         brushes=wx.Brush(wx.Colour(colour)))
            memory.SelectObject(wx.NullBitmap)
            dc.DrawBitmap(bitmap, target.x, target.y)

    def level_y(self, meter, db):
        ratio = 1.0 - (min(max(db, FLOOR), 0.0) / FLOOR) ** METER_CURVE
        return meter.y + meter.height * (1.0 - ratio)

    def draw_speaker(self, gc, cx, cy, master, scale=1.0):
        colour = self.accent if master else RACK['dim']
        gc.PushState()
        gc.Translate(cx, cy)
        gc.Scale(scale, scale)
        cx = cy = 0
        gc.SetPen(wx.TRANSPARENT_PEN)
        gc.SetBrush(wx.Brush(wx.Colour(colour)))
        path = gc.CreatePath()
        path.MoveToPoint(cx - 9, cy - 3)
        path.AddLineToPoint(cx - 4, cy - 3)
        path.AddLineToPoint(cx + 2, cy - 9)
        path.AddLineToPoint(cx + 2, cy + 9)
        path.AddLineToPoint(cx - 4, cy + 3)
        path.AddLineToPoint(cx - 9, cy + 3)
        path.CloseSubpath()
        gc.FillPath(path)
        gc.SetPen(gc.CreatePen(wx.GraphicsPenInfo(wx.Colour(colour)).Width(1.5)
                               .Cap(wx.CAP_ROUND)))
        gc.SetBrush(wx.TRANSPARENT_BRUSH)
        for radius in (5, 9):
            arc = gc.CreatePath()
            arc.AddArc(cx + 2, cy, radius, -0.8, 0.8, True)
            gc.StrokePath(arc)
        gc.PopState()
