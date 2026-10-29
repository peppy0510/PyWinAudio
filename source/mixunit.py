# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com
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
from rackui import get_control_tone
from rackui import get_pen
from rackui import mix
from rackui import set_font
from units import EAR
from units import FOLD
from units import FOLDED
from units import INSET
from units import TIGHT_PAD


COLUMN = 64
COLUMN_GAP = 1
COLUMN_HEIGHT = 192
RULE_GAP = 8
FOOT = 45
HEADER = HEADER_BAND + 1 + TIGHT_PAD
ICON = 16
FLOOR = -60.0
METER_CURVE = 0.6

LOW = '#2fd2e8'
MID = '#ffb04d'
HIGH = '#ff7a33'
SCALE_TEXT = '#3fb6c6'
# session volume is a linear factor, so 20 log10 is dB
TAPER_FLOOR = -60.0
FADER_MARKS = (0, -6, -12, -20, -30, -40, -60)
METER_GROUND = RACK['lcd']
DOT = 6
SEG = 2
SEG_GAP = 1
SEGMENT_OFF = 0.84
CAP_HEIGHT = 10
MUTE_SIZE = 20
NAME_GAP = 19
WINDOW = 0.3
ATTACK = 0.04
RELEASE = 0.35
DEADBAND = 0.6


class ChannelFader(Control):

    cursor = wx.CURSOR_SIZENS

    on_move = staticmethod(lambda: None)

    def __init__(self, channel, accent):
        super().__init__()
        self.channel = channel
        self.accent = accent
        self.origin = None

    @staticmethod
    def to_ratio(volume):
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
        # repaint now, or the cap stays put until release
        self.on_move()

    def on_dclick(self, point):
        self.channel.set_volume(1.0)
        self.origin = None
        self.on_move()

    def on_up(self, point):
        self.pressed = False
        self.origin = None

    def draw(self, gc, accent):
        rect = self.rect
        cx = rect.x + rect.width / 2
        volume = self.channel.get_volume()
        fill_rect(gc, RACK['track'], cx - 1, rect.y, 2, rect.height, 1)
        y = self.to_y(volume)
        fill = mix(get_control_tone(self.accent), '#000000', 0.25)
        fill_rect(gc, fill, cx - 1, y, 2, rect.y + rect.height - y, 1)
        for db in FADER_MARKS:
            ty = round(self.to_y(10 ** (db / 20)))
            fill_rect(gc, RACK['faint'], cx - 6, ty, 4, 1)
            fill_rect(gc, RACK['faint'], cx + 2, ty, 4, 1)
            draw_text(gc, str(abs(db)), rect.x - 2, ty - 5, 6, SCALE_TEXT, align='right')
        lit = self.hovered or self.pressed
        cap = wx.Rect(round(rect.x + 3), round(y - CAP_HEIGHT / 2), rect.width - 6, CAP_HEIGHT)
        gc.SetPen(wx.TRANSPARENT_PEN)
        gc.SetBrush(wx.Brush(wx.Colour('#a9adb3' if lit else '#868a91')))
        gc.DrawRoundedRectangle(cap.x, cap.y, cap.width, cap.height, 2)
        fill_rect(gc, '#2a2d32', cap.x + 3, y - 0.5, cap.width - 6, 1)


class Column:

    def __init__(self, unit, channel, master):
        self.channel = channel
        self.master = master
        self.fader = ChannelFader(channel, FACES['master'][1] if master else LOW)
        self.fader.on_move = unit.repaint
        self.mute = Button('M', self.toggle_mute, active=lambda: self.channel.get_mute())
        self.mute.tip = 'Mute ' + channel.name
        self.rect = wx.Rect()
        self.meter = wx.Rect()

    def adopt(self, channel):
        # keep columns across refreshes; new ones flashed empty and dropped the dragged fader
        self.channel = channel
        self.fader.channel = channel

    def toggle_mute(self):
        self.channel.set_mute(not self.channel.get_mute())

    def layout(self, x, y):
        self.rect = wx.Rect(x, y, COLUMN, COLUMN_HEIGHT)
        top = y + 40 + NAME_GAP + CAP_HEIGHT // 2
        bottom = y + COLUMN_HEIGHT - FOOT - CAP_HEIGHT // 2
        self.meter = wx.Rect(x + 9, top - CAP_HEIGHT // 2, DOT, bottom - top + CAP_HEIGHT)
        self.fader.rect = wx.Rect(x + 34, top, 22, bottom - top)
        # 21 px so the even-width rim centres on the 2 px track (measured)
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
        rect = self.rect
        self.rack.RefreshRect(wx.Rect(rect.x, rect.y - self.rack.offset, rect.width,
                                      rect.height), False)

    def toggle_fold(self):
        self.data['folded'] = not self.folded
        if not self.folded:
            self.refresh()
        self.rack.on_unit_change(None)

    def refresh(self):
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
        # session meters give momentary peaks; follow a short envelope or the top segment flickers
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
        return sum(1 for top, edge, lit, dark in self.get_segments(meter) if db >= edge)

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
        self.fold.rect = wx.Rect(left - 5, rect.y + (FOLDED - FOLD) // 2, FOLD, FOLD)
        if self.folded:
            return
        per_row = self.get_per_row(rect.width)
        for index, column in enumerate(self.columns):
            row, place = divmod(index, per_row)
            column.layout(rect.x + TIGHT_PAD + place * (COLUMN + COLUMN_GAP),
                          rect.y + HEADER + row * (COLUMN_HEIGHT + COLUMN_GAP))

    def get_icon(self, path):
        if path in self.icons:
            return self.icons[path]
        bitmap = None
        # wxPython 4.3 reads wx.Bitmap(icon) as an XPM list and fails
        try:
            image = None
            if path.lower().endswith('.ico'):
                image = wx.Image(path, wx.BITMAP_TYPE_ICO)
            else:
                # an exe with no icon resource (ShellExperienceHost) makes wx pop an error box
                quiet = wx.LogNull()
                icon = wx.Icon(wx.IconLocation(path, 0))
                del quiet
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
        return f'{count} program{"" if count == 1 else "s"}'

    def draw(self, gc):
        rect = self.rect
        draw_faceplate(gc, rect.x, rect.y, rect.width, rect.height, self.face, EAR, self.accent)
        self.draw_speaker(gc, rect.x + EAR + INSET + FOLD + 8 - 0.6, rect.y + FOLDED / 2, False, 0.62)
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
            fill_rect(gc, get_control_tone(self.accent), rect.x + 6, rect.y, rect.width - 12, 2,
                      1)
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
        fill_rect(gc, RACK['line'], rect.x, rect.y + 41 + RULE_GAP + 1, rect.width, 1)
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
        value = '-inf' if volume <= 1e-6 else f'{20 * math.log10(min(volume, 1.0)):.1f}'
        x, middle = column.value
        draw_text(gc, value, x, middle - 5, 7, RACK['warn'] if muted else RACK['text'], bold=True)
        column.mute.draw(gc, RACK['warn'])

    def get_segments(self, meter):
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
        # compose off screen: painting the ground first flickered empty bars
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
        colour = get_control_tone(self.accent) if master else RACK['dim']
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
