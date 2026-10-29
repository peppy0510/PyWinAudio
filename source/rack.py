# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com
'''


import dsp
import eapo
import math
import os
import threading
import time
import wx

from rackui import FACES
from rackui import RACK
from rackui import Button
from rackui import Power
from rackui import Segment
from rackui import draw_faceplate
from rackui import draw_rails
from rackui import draw_text
from rackui import draw_title
from rackui import fill_rect
from rackui import fit_text
from rackui import get_db_text
from rackui import set_font
from units import ADDABLE
from units import FOLD
from units import FOLDED
from units import EAR
from units import INSET
from units import TITLES
from units import U
from units import build_unit
from units import migrate_automaster
from units import make_unit
from mixunit import MixerUnit
from utilities import Canvas
from utilities import call_painted


MARGIN = 8
GAP = 3
MIXER_FPS = 30
MIXER_REFRESH = 1000
MIXER_FALL = 15.0
WHEEL_STEP = 60
SCROLLBAR = 4
SCROLLBAR_INSET = (MARGIN - SCROLLBAR) // 2
SCROLLBAR_COLOUR = '#3a3f46'
SCROLL_MIN = 24
SCROLL_HOLD = 0.7
SCROLL_FADE = 0.4
SCROLL_STEP = 16
TWO_COLUMNS = 820
THREE_COLUMNS = 1240


def split_columns(heights, count):
    prefix = [0]
    for height in heights:
        prefix.append(prefix[-1] + height)
    n = len(heights)
    best = {1: prefix[:]}
    cut = {1: [0] * (n + 1)}
    for c in range(2, count + 1):
        best[c], cut[c] = [], []
        for i in range(n + 1):
            # on ties cut later, so empty columns end up last
            choice = min(range(i, -1, -1), key=lambda j: max(best[c - 1][j], prefix[i] - prefix[j]))
            best[c].append(max(best[c - 1][choice], prefix[i] - prefix[choice]))
            cut[c].append(choice)
    starts, end = [], n
    for c in range(count, 0, -1):
        starts.insert(0, cut[c][end])
        end = cut[c][end]
    return starts


class MasterUnit:

    height = FOLDED

    def __init__(self, rack):
        self.rack = rack
        self.rect = wx.Rect()
        self.face, self.accent = FACES['master']
        self.power = Power(lambda: rack.power, rack.set_power)
        self.link = Button('Link', rack.on_link, confirm='Replace config.txt?')

    def get_controls(self):
        return [self.power, self.link] if self.rack.state == 'unlinked' else [self.power]

    def layout(self, gc, rect):
        self.rect = rect
        left = rect.x + EAR + INSET
        middle = rect.y + FOLDED // 2
        self.power.rect = wx.Rect(left + FOLD, middle - 7, 14, 14)
        width = self.link.get_width(gc)
        right = rect.x + rect.width - EAR - INSET + 2
        self.link.rect = wx.Rect(right - width, middle - Button.HEIGHT // 2, width,
                                 Button.HEIGHT)
        self.text_right = (self.link.rect.x - 12 if self.rack.state == 'unlinked'
                           else right)

    def get_status(self):
        state = self.rack.state
        if state == 'missing':
            return 'Equalizer APO is not installed', RACK['warn']
        if state == 'unlinked':
            return 'Not linked. Link takes over config.txt and keeps a copy', RACK['warn']
        if not self.rack.power:
            return 'Switched off. Sound passes through untouched', RACK['dim']
        return 'ACTIVE', RACK['dim']

    def draw(self, gc):
        rect = self.rect
        draw_faceplate(gc, rect.x, rect.y, rect.width, rect.height, self.face, EAR, self.accent)
        left = self.power.rect.x + 22
        right = self.text_right
        if self.rack.state == 'linked' and self.rack.power:
            boost = self.rack.get_peak_boost() + self.rack.get_preamp()
            text = 'EQ BOOST %s' % get_db_text(boost)
            width = draw_text(gc, text, right, rect.y + FOLDED / 2 - 6, 8, RACK['dim'],
                              align='right', engraved=True)[0]
            right -= width + 16
        status, tone = self.get_status()
        draw_title(gc, left, rect.y, 'PyWinAudio Rack', status, tone, max(0, right - left))
        for control in self.get_controls():
            control.draw(gc, self.accent)


class AddSlot:

    height = U + 30

    def __init__(self, rack):
        self.rack = rack
        self.rect = wx.Rect()
        self.builtin = Button('Built-in  \u25be', self.on_builtin)
        self.buttons = [self.builtin, Button('VST plugin…', lambda: rack.add('vst'))]

    def on_builtin(self):
        menu = wx.Menu()
        for kind in ADDABLE:
            if kind == 'vst':
                continue
            item = menu.Append(wx.ID_ANY, TITLES[kind])
            self.rack.Bind(wx.EVT_MENU, lambda event, kind=kind: self.rack.add(kind), item)
        rect = self.builtin.rect
        self.rack.PopupMenu(menu, wx.Point(rect.x, rect.y + rect.height - self.rack.offset))
        menu.Destroy()

    def get_controls(self):
        return self.buttons

    LABEL = 'ADD A DEVICE'
    LABEL_SIZE = 8.5
    MARGIN = 8

    def layout(self, gc, rect):
        left = rect.x + EAR + INSET
        right = rect.x + rect.width - EAR - INSET
        set_font(gc, self.LABEL_SIZE, RACK['dim'], bold=True)
        label = int(math.ceil(gc.GetTextExtent(self.LABEL)[0]))
        top = rect.y + self.MARGIN
        x, y = left + label + 12, top
        for button in self.buttons:
            width = button.get_width(gc)
            if x + width > right and x > left:
                x, y = left, y + Button.HEIGHT + 6
            button.rect = wx.Rect(x, y, width, Button.HEIGHT)
            x += width + 6
        self.label_y = top + Button.HEIGHT / 2 - 6
        self.height = y + Button.HEIGHT + self.MARGIN - rect.y
        self.rect = wx.Rect(rect.x, rect.y, rect.width, self.height)

    def draw(self, gc):
        rect = self.rect
        inner = rect
        gc.SetPen(wx.Pen(wx.Colour(RACK['line']), 1, wx.PENSTYLE_SHORT_DASH))
        gc.SetBrush(wx.TRANSPARENT_BRUSH)
        gc.DrawRoundedRectangle(inner.x + 0.5, inner.y + 0.5, inner.width - 1,
                                inner.height - 1, 4)
        draw_text(gc, self.LABEL, rect.x + EAR + INSET, self.label_y, self.LABEL_SIZE,
                  RACK['dim'], bold=True)
        for button in self.buttons:
            button.draw(gc, FACES['master'][1])


class AnalyzerSlot:

    height = 0

    def __init__(self, rack):
        self.rack = rack
        self.rect = wx.Rect()

    def get_height(self, width):
        return self.rack.analyzer.get_height(width)

    def get_controls(self):
        return []

    def layout(self, gc, rect):
        self.rect = rect

    def draw(self, gc):
        pass


class RemoveConfirm:

    def __init__(self, rack, unit):
        self.rack = rack
        self.unit = unit
        self.remove = Button('Remove', lambda: rack.confirm_remove(), active=lambda: True)
        self.cancel = Button('Cancel', lambda: rack.cancel_remove())

    def get_controls(self):
        return [self.remove, self.cancel]

    def layout(self, gc):
        rect = self.unit.rect
        right = rect.x + rect.width - EAR - INSET
        middle = rect.y + rect.height // 2
        x = right
        for button in (self.remove, self.cancel):
            width = button.get_width(gc)
            x -= width
            button.rect = wx.Rect(x, middle - Button.HEIGHT // 2, width, Button.HEIGHT)
            x -= 8

    def draw(self, gc):
        rect = self.unit.rect
        gc.SetPen(wx.TRANSPARENT_PEN)
        gc.SetBrush(wx.Brush(wx.Colour(10, 11, 13, 235)))
        gc.DrawRectangle(rect.x + EAR, rect.y, rect.width - EAR * 2, rect.height)
        left = rect.x + EAR + INSET
        limit = max(0, self.cancel.rect.x - left - 16)
        middle = rect.y + rect.height / 2
        set_font(gc, 10.5, RACK['text'], bold=True)
        title = fit_text(gc, 'Remove %s?' % self.unit.get_title().upper(), limit)
        draw_text(gc, title, left, middle - 17, 10.5, RACK['text'], bold=True)
        set_font(gc, 8, RACK['dim'])
        draw_text(gc, fit_text(gc, 'Its settings go with it', limit), left, middle + 2, 8,
                  RACK['dim'])
        self.remove.draw(gc, RACK['warn'])
        self.cancel.draw(gc, RACK['warn'])


class Pacer(threading.Thread):
    # wx.Timer snaps to the 15.6 ms tick; a thread paces frames evenly

    def __init__(self, view):
        super().__init__(name='mixer-pacer', daemon=True)
        self.view = view
        self.running = True
        self.pending = False

    def run(self):
        interval = 1.0 / MIXER_FPS
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
                    call_painted(self.view, self.view.tick)
                except Exception:
                    return


class RackView(Canvas):

    def __init__(self, parent, theme, chain, power, on_change, mixer=None):
        super().__init__(parent, theme)
        self.on_change = on_change
        self.power = power
        self.state, self.folder = eapo.get_state()
        self.master = MasterUnit(self)
        self.mixer = MixerUnit(self, mixer if mixer is not None else {})
        self.slot = AddSlot(self)
        self.analyzer = None
        self.analyzer_slot = AnalyzerSlot(self)
        self.columns = 1
        # undo a bypass left by a crash during an A/B compare
        from automastermeter import READER
        READER.set_bypass(False)
        # rewrite the engine line so it loads the newest (or renamed) DLL
        if [data for data in chain if migrate_automaster(data)]:
            wx.CallAfter(lambda: self and self.on_unit_change())
        self.units = [build_unit(data, self) for data in chain]
        self.offset = 0
        self.total = 0
        self.active = None
        self.hovered = None
        self.thumb = None
        self.thumb_drag = None
        self.boost = None
        self.confirm = None
        self.meter_boxes = []
        self.bottom_space = 0
        self.meters_y = 0
        self.top_gap = MARGIN
        self.wide = True
        self.on_scroll = None
        self.notified = None
        self.scrolled_at = 0.0
        self.near_edge = False
        self.fade_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_scroll_fade, self.fade_timer)
        # WS_EX_COMPOSITED repaints the whole canvas for one meter (92 % of a core)
        self.SetDoubleBuffered(False)
        self.update_box = None
        self.last_tick = time.perf_counter()
        self.mixer.refresh()
        self.refresher = wx.CallLater(MIXER_REFRESH, self.refresh_mixer)
        self.pacer = Pacer(self)
        self.pacer.start()

        self.Bind(wx.EVT_LEFT_DOWN, self.on_down)
        self.Bind(wx.EVT_LEFT_DCLICK, self.on_dclick)
        self.Bind(wx.EVT_LEFT_UP, self.on_up)
        self.Bind(wx.EVT_MOTION, self.on_motion)
        self.Bind(wx.EVT_LEAVE_WINDOW, self.on_leave)
        self.Bind(wx.EVT_MOUSEWHEEL, self.on_wheel)
        self.Bind(wx.EVT_MOUSE_CAPTURE_LOST, self.on_capture_lost)
        self.Bind(wx.EVT_SIZE, lambda event: (self.clamp(), event.Skip()))

    def get_chain(self):
        return [unit.data for unit in self.units]

    def get_peak_boost(self):
        if self.boost is None:
            self.boost = dsp.get_peak_boost([unit.data for unit in self.units])
        return self.boost

    def get_preamp(self):
        return sum(unit.data['gain'] for unit in self.units
                   if unit.data['kind'] == 'preamp' and unit.data.get('on', True))

    def get_plugin_folder(self):
        for unit in self.units:
            path = unit.data.get('path') if unit.data['kind'] == 'vst' else None
            if path:
                return os.path.dirname(path)
        install = eapo.get_install_path()
        for folder in (r'C:\Program Files\VSTPlugIns', r'C:\Program Files\Steinberg\VSTPlugins',
                       os.path.join(install, 'VSTPlugins') if install else ''):
            if folder and os.path.isdir(folder):
                return folder
        return ''

    def on_unit_change(self, unit=None):
        self.boost = None
        self.Refresh()
        self.on_change()

    def set_power(self, value):
        self.power = bool(value)
        self.on_unit_change()

    def refresh_state(self):
        self.state, self.folder = eapo.get_state()
        self.Refresh()

    def on_link(self):
        if self.state != 'unlinked':
            return
        imported = eapo.link(self.folder)
        # relinking would import the restored lines again; skip what the rack already has
        present = [eapo.render_unit(unit.data) for unit in self.units]
        plugins = {unit.data['path'].lower() for unit in self.units
                   if unit.data['kind'] == 'vst' and unit.data.get('path')}
        fresh = [data for data in imported if eapo.render_unit(data) not in present and
                 not (data['kind'] == 'vst' and data['path'].lower() in plugins)]
        self.units = [build_unit(data, self) for data in fresh] + self.units
        self.refresh_state()
        self.on_unit_change()

    def on_unlink(self):
        if self.state != 'linked':
            return
        eapo.unlink(self.folder)
        try:
            os.remove(os.path.join(self.folder, eapo.OWN_FILE))
        except OSError:
            pass
        self.refresh_state()

    def add(self, kind):
        self.cancel_remove()
        unit = build_unit(make_unit(kind), self)
        # add a VST only after a file is picked; an empty plate showed while choosing
        path = unit.pick_path() if kind == 'vst' else None
        if kind == 'vst' and path is None:
            return
        self.units.append(unit)
        if path is not None:
            unit.load(path)
        if kind == 'automaster' and os.path.exists(unit.data['path']):
            unit.load(unit.data['path'])
        self.on_unit_change()
        wx.CallAfter(self.reveal, unit)

    def remove(self, unit):
        if unit in self.units:
            self.reset_pointer()
            self.confirm = RemoveConfirm(self, unit)
            self.Refresh()

    def confirm_remove(self):
        confirm, self.confirm = self.confirm, None
        if confirm is None or confirm.unit not in self.units:
            return
        unit = confirm.unit
        if hasattr(unit, 'close'):
            unit.close()
        self.units.remove(unit)
        self.reset_pointer()
        self.on_unit_change()

    def cancel_remove(self):
        if self.confirm is None:
            return False
        self.confirm = None
        self.reset_pointer()
        self.Refresh()
        return True

    def move(self, unit, delta):
        index = self.units.index(unit)
        target = index + delta
        if 0 <= target < len(self.units):
            self.cancel_remove()
            self.units[index], self.units[target] = self.units[target], self.units[index]
            self.on_unit_change()

    def refresh_mixer(self):
        if not self:
            return
        if self.IsShownOnScreen() and not self.GetTopLevelParent().IsIconized() and \
                not self.mixer.folded and self.mixer.refresh():
            self.Refresh()
        self.refresher = wx.CallLater(MIXER_REFRESH, self.refresh_mixer)

    def tick(self):
        if not self:
            return
        self.pacer.pending = False
        now = time.perf_counter()
        elapsed = min(0.2, now - self.last_tick)
        self.last_tick = now
        if not self.IsShownOnScreen() or self.GetTopLevelParent().IsIconized():
            return
        self.meter_boxes = []
        self.meter_ticks = getattr(self, 'meter_ticks', 0) + 1
        if self.meter_ticks % 3 == 0:
            room = self.get_room()
            for unit in self.units:
                rect = getattr(unit, 'meter_rect', None)
                if rect is None or unit.folded or not unit.update_meters(elapsed * 3):
                    continue
                box = wx.Rect(rect.x, rect.y - self.offset, rect.width, rect.height)
                if box.y + box.height >= 0 and box.y <= room:
                    box.Inflate(2, 2)
                    if unit.knobs and self.confirm is None:
                        self.meter_boxes.append((box, unit))
                    self.RefreshRect(box, False)
        if self.mixer.folded:
            return
        changed = self.mixer.update_levels(elapsed, MIXER_FALL)
        # repaint only meters whose lit count changed
        room = self.get_room()
        for column in self.mixer.columns:
            if column.channel.key not in changed:
                continue
            meter = column.meter
            box = wx.Rect(meter.x, meter.y - self.offset, meter.width, meter.height)
            if box.y + box.height < 0 or box.y > room:
                continue
            self.meter_boxes.append((box, self.mixer))
            self.RefreshRect(box, False)

    def close(self):
        self.pacer.running = False
        self.fade_timer.Stop()
        if self.refresher is not None and self.refresher.IsRunning():
            self.refresher.Stop()
        for unit in self.units:
            if hasattr(unit, 'close'):
                unit.close()

    def get_blocks(self):
        blocks = [self.mixer, self.master] + self.units + [self.slot]
        if self.analyzer is not None and self.columns > 1:
            if self.analyzer.pinned:
                blocks.insert(0, self.analyzer_slot)
            else:
                blocks.append(self.analyzer_slot)
        return blocks

    def get_controls(self):
        if self.confirm is not None:
            for control in self.confirm.get_controls():
                yield control
        for block in self.get_blocks():
            if self.confirm is not None and block is self.confirm.unit:
                continue
            for control in block.get_controls():
                yield control

    def get_column_count(self, width):
        if not self.wide or width < TWO_COLUMNS:
            return 1
        return 3 if width >= THREE_COLUMNS else 2

    def measure(self, gc, block, width):
        if hasattr(block, 'get_height'):
            return block.get_height(width)
        # ADD wraps its buttons, so lay it out to measure
        block.layout(gc, wx.Rect(MARGIN, 0, width, block.height))
        return block.rect.height

    def set_wide(self, wide):
        if wide != self.wide:
            self.wide = wide
            self.Refresh()

    def layout(self, gc, width):
        self.columns = self.get_column_count(width)
        blocks = self.get_blocks()
        count = min(self.columns, len(blocks))
        inner = width - MARGIN * 2
        starts = [0]
        while count > 1:
            base = (inner - GAP * (count - 1)) // count
            starts = split_columns([self.measure(gc, block, base) for block in blocks], count)
            # drop empty columns: one tall plate can leave the last ones bare
            used = len(set(starts) - {len(blocks)})
            if used == count:
                break
            count = used
        if count == 1:
            starts = [0]
        # spare pixels go to the first columns so the right edge meets the margin
        base, extra = divmod(inner - GAP * (count - 1), count)
        widths = [base + (1 if index < extra else 0) for index in range(count)]
        bottom = self.top_gap
        x = MARGIN
        for column, span in enumerate(widths):
            end = starts[column + 1] if column + 1 < count else len(blocks)
            y = self.top_gap
            for block in blocks[starts[column]:end]:
                height = block.get_height(span) if hasattr(block, 'get_height') else block.height
                block.layout(gc, wx.Rect(x, y, span, height))
                y += block.rect.height + GAP
            bottom = max(bottom, y)
            x += span + GAP
        y = bottom
        self.meters_y = y
        self.total = (y + self.bottom_space if self.bottom_space else y - GAP) + MARGIN
        if self.confirm is not None:
            self.confirm.layout(gc)
        for control in self.get_controls():
            if isinstance(control, Button):
                control.on_reset = self.Refresh

    def get_room(self):
        return self.GetClientSize().height

    def clamp(self):
        # wx.Point and wx.Rect reject floats, and wheel and drag math yield them
        self.offset = int(round(max(0, min(self.offset, self.total - self.get_room()))))

    def reveal(self, unit):
        bottom = unit.rect.y + unit.rect.height + MARGIN + self.slot.height
        if bottom - self.offset > self.get_room():
            self.offset = bottom - self.get_room()
            self.clamp()
            self.Refresh()

    def draw(self, gc, width, height):
        # the scrollbar overlays the margin so the rack width never changes
        rack_width = width
        self.layout(gc, rack_width)
        self.clamp()
        rect = self.analyzer_slot.rect if self.columns > 1 else None
        key = (self.offset, self.meters_y, rect and tuple(rect))
        if self.on_scroll is not None and self.notified != key:
            self.notified = key
            wx.CallAfter(self.on_scroll)
        fill_rect(gc, RACK['bg'], 0, 0, width, height)
        gc.PushState()
        gc.Translate(0, -self.offset)
        draw_rails(gc, MARGIN, 0, rack_width - MARGIN * 2, max(self.total, self.offset + height),
                   EAR)
        # partial repaints draw only the blocks they touch; EQ curves are costly
        box = self.update_box
        top, bottom = self.offset, self.offset + height
        if box is not None:
            top, bottom = max(top, box.y + self.offset), min(bottom, box.y + box.height + self.offset)
        for block in self.get_blocks():
            rect = block.rect
            if rect.y + rect.height < top or rect.y > bottom:
                continue
            block.draw(gc)
        if self.confirm is not None:
            self.confirm.draw(gc)
        gc.PopState()
        self.draw_scrollbar(gc, width, height)

    def on_paint(self, event):
        region = self.GetUpdateRegion()
        box = region.GetBox()
        boxes, self.meter_boxes = self.meter_boxes, []
        if boxes and self.is_meter_only(region, boxes):
            dc = wx.PaintDC(self)
            painted = set()
            for target, owner in boxes:
                if owner not in painted and target.Intersects(box):
                    painted.add(owner)
                    owner.paint_levels(dc, self.offset, box)
            return
        self.update_box = box
        super().on_paint(event)
        self.update_box = None

    def is_meter_only(self, region, boxes):
        pieces = wx.RegionIterator(region)
        while pieces.HaveRects():
            piece = pieces.GetRect()
            if not any(target.Contains(piece) for target, owner in boxes):
                return False
            pieces.Next()
        return True

    def draw_scrollbar(self, gc, width, height):
        self.thumb = None
        if self.total <= height:
            return
        size = max(SCROLL_MIN, height * height / self.total)
        top = (height - size) * self.offset / max(1, self.total - height)
        self.thumb = wx.Rect(width - MARGIN, round(top), MARGIN, round(size))
        alpha = self.get_scroll_alpha()
        if alpha <= 0:
            return
        tone = wx.Colour(SCROLLBAR_COLOUR)
        fill_rect(gc, wx.Colour(tone.Red(), tone.Green(), tone.Blue(), int(255 * alpha)),
                  width - SCROLLBAR_INSET - SCROLLBAR, self.thumb.y, SCROLLBAR, self.thumb.height, 2)

    def get_scroll_alpha(self):
        if self.thumb_drag is not None or self.near_edge:
            return 1.0
        elapsed = time.perf_counter() - self.scrolled_at - SCROLL_HOLD
        if elapsed <= 0:
            return 1.0
        progress = min(1.0, elapsed / SCROLL_FADE)
        return (1.0 - progress) ** 2

    def on_scroll_fade(self, event):
        if not self:
            return
        width, height = self.GetClientSize()
        self.RefreshRect(wx.Rect(width - MARGIN, 0, MARGIN, height), False)
        if self.get_scroll_alpha() <= 0:
            self.fade_timer.Stop()

    def show_scrollbar(self):
        self.scrolled_at = time.perf_counter()
        if not self.fade_timer.IsRunning():
            self.fade_timer.Start(SCROLL_STEP)

    def set_near_edge(self, near):
        if near != self.near_edge:
            self.near_edge = near
            if near:
                self.Refresh()
            else:
                self.show_scrollbar()

    def to_rack(self, position):
        return wx.Point(position.x, position.y + self.offset)

    def find(self, point):
        for control in self.get_controls():
            if control.contains(point):
                return control
        return None

    def set_hover(self, control, point):
        changed = False
        if control is not self.hovered:
            if self.hovered is not None:
                self.hovered.hovered = False
            self.hovered = control
            if control is not None:
                control.hovered = True
            changed = True
        if isinstance(control, Segment) and control.track(point):
            changed = True
        cursor = control.cursor if control is not None else wx.CURSOR_ARROW
        self.SetCursor(wx.Cursor(cursor))
        tip = control.tip if control is not None else ''
        if tip != (self.GetToolTipText() or ''):
            self.SetToolTip(tip or None)
        if changed:
            self.Refresh()

    def on_down(self, event):
        position = event.GetPosition()
        if self.thumb is not None and self.thumb.Contains(position):
            self.thumb_drag = (position.y, self.offset)
            self.CaptureMouse()
            self.Refresh()
            return
        point = self.to_rack(position)
        control = self.find(point)
        if self.confirm is not None and control not in self.confirm.get_controls():
            self.cancel_remove()
            control = self.find(point)
        if control is None:
            return
        self.active = control
        control.on_down(point, event.ShiftDown())
        if not self.HasCapture():
            self.CaptureMouse()
        self.Refresh()

    def on_dclick(self, event):
        point = self.to_rack(event.GetPosition())
        control = self.find(point)
        if control is None:
            return
        control.on_dclick(point)
        # the second press of a double click arrives only as a dclick
        if isinstance(control, (Button, Power, Segment)):
            control.on_down(point, event.ShiftDown())
            self.active = control
            if not self.HasCapture():
                self.CaptureMouse()
        self.Refresh()

    def on_up(self, event):
        if self.HasCapture():
            self.ReleaseMouse()
        if self.thumb_drag is not None:
            self.thumb_drag = None
            self.show_scrollbar()
            self.Refresh()
            return
        control, self.active = self.active, None
        if control is not None:
            control.on_up(self.to_rack(event.GetPosition()))
            self.Refresh()

    def on_motion(self, event):
        position = event.GetPosition()
        if self.thumb_drag is not None:
            top, offset = self.thumb_drag
            height = self.get_room()
            size = max(SCROLL_MIN, height * height / max(1, self.total))
            span = max(1, height - size)
            self.offset = offset + (position.y - top) * (self.total - height) / span
            self.clamp()
            self.Refresh()
            return
        self.set_near_edge(self.total > self.get_room() and
                           position.x >= self.GetClientSize().width - MARGIN)
        point = self.to_rack(position)
        if self.active is not None:
            self.active.on_drag(point, event.ShiftDown())
            return
        self.set_hover(self.find(point), point)

    def on_leave(self, event):
        if self.thumb_drag is None:
            self.set_near_edge(False)
        if self.active is None:
            self.set_hover(None, wx.Point(-1, -1))

    def on_wheel(self, event):
        if self.active is not None:
            return
        steps = event.GetWheelRotation() / (event.GetWheelDelta() or 120)
        # the wheel never moves faders: scrolling past one changed the volume
        self.offset -= steps * WHEEL_STEP
        self.clamp()
        self.show_scrollbar()
        self.Refresh()
        self.set_hover(self.find(self.to_rack(event.GetPosition())),
                       self.to_rack(event.GetPosition()))

    def on_capture_lost(self, event):
        self.reset_pointer()

    def reset_pointer(self):
        if self.active is not None:
            self.active.pressed = False
            if hasattr(self.active, 'origin'):
                self.active.origin = None
        self.active = None
        self.thumb_drag = None
        if self.hovered is not None:
            self.hovered.hovered = False
        self.hovered = None
