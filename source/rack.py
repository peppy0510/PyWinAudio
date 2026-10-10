# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com

랙 한 장. 맨 위에 주 장치, 그 아래로 사용자가 꽂은 장치들, 맨 끝에 빈 칸.
모두 이 캔버스 하나가 그리고, 누름도 여기서 받아 해당 조작부에 넘긴다.

세로 스크롤은 직접 민다. 휠은 언제나 랙을 굴린다 — 손잡이는 끌어서만 돌아간다.
그래야 굴리다가 지나가는 손잡이가 몰래 바뀌는 일이 없다.
'''


import dsp
import eapo
import os
import wx

from rackui import FACES
from rackui import RACK
from rackui import Button
from rackui import Power
from rackui import Segment
from rackui import draw_faceplate
from rackui import draw_rails
from rackui import draw_text
from rackui import fill_rect
from rackui import fit_text
from rackui import get_db_text
from rackui import set_font
from units import ADDABLE
from units import EAR
from units import INSET
from units import TITLES
from units import U
from units import build_unit
from units import make_unit
from utilities import Canvas


MARGIN = 14
GAP = 3
WHEEL_STEP = 60
SCROLLBAR = 8
SCROLL_MIN = 30


class MasterUnit:
    '''랙의 머리. 랙 전체를 켜고 끄고, Equalizer APO 와 이어졌는지 알린다.'''

    height = 2 * U

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
        middle = rect.y + rect.height / 2
        self.power.rect = wx.Rect(left, round(middle - 7), 14, 14)
        width = self.link.get_width(gc)
        right = rect.x + rect.width - EAR - INSET
        self.link.rect = wx.Rect(right - width, round(middle - Button.HEIGHT / 2), width,
                                 Button.HEIGHT)
        self.text_right = (self.link.rect.x - 16 if self.rack.state == 'unlinked'
                           else right)

    def get_status(self):
        state = self.rack.state
        if state == 'missing':
            return 'Equalizer APO is not installed', RACK['warn']
        if state == 'unlinked':
            return 'Not linked. Link takes over config.txt and keeps a copy', RACK['warn']
        if not self.rack.power:
            return 'Switched off. Sound passes through untouched', RACK['dim']
        return 'Writing %s' % os.path.join(self.rack.folder, eapo.OWN_FILE), RACK['dim']

    def draw(self, gc):
        rect = self.rect
        draw_faceplate(gc, rect.x, rect.y, rect.width, rect.height, self.face, EAR)
        left = self.power.rect.x + 22
        middle = rect.y + rect.height / 2
        title_width = draw_text(gc, 'PYWINAUDIO', left, middle - 17, 12, RACK['text'],
                                bold=True, engraved=True)[0]
        draw_text(gc, 'RACK', left + title_width + 8, middle - 14, 8.5, self.accent,
                  bold=True, engraved=True)
        status, tone = self.get_status()
        set_font(gc, 8, tone)
        draw_text(gc, fit_text(gc, status, max(0, self.text_right - left)), left,
                  middle + 3, 8, tone, engraved=True)

        if self.rack.state == 'linked' and self.rack.power:
            boost = self.rack.get_peak_boost()
            text = 'PEAK %s' % get_db_text(boost + self.rack.get_preamp())
            draw_text(gc, text, self.text_right, middle - 15, 8, RACK['dim'], align='right',
                      engraved=True)
        for control in self.get_controls():
            control.draw(gc, self.accent)


class AddSlot:
    '''비어 있는 랙 칸. 꽂을 장치를 고르는 단추가 줄지어 있다.'''

    height = U + 30

    def __init__(self, rack):
        self.rack = rack
        self.rect = wx.Rect()
        self.buttons = [Button(TITLES[kind] if kind != 'vst' else 'VST plugin…',
                               lambda kind=kind: rack.add(kind)) for kind in ADDABLE]

    def get_controls(self):
        return self.buttons

    def layout(self, gc, rect):
        self.rect = rect
        left = rect.x + EAR + INSET
        right = rect.x + rect.width - EAR - INSET
        x, y = left, rect.y + 30
        for button in self.buttons:
            width = button.get_width(gc)
            if x + width > right and x > left:
                x, y = left, y + Button.HEIGHT + 6
            button.rect = wx.Rect(x, y, width, Button.HEIGHT)
            x += width + 6
        # 단추가 몇 줄로 접히는지는 폭이 정한다. 접힌 만큼 칸이 자란다.
        self.height = max(U + 30, y + Button.HEIGHT + 12 - rect.y)
        self.rect = wx.Rect(rect.x, rect.y, rect.width, self.height)

    def draw(self, gc):
        rect = self.rect
        inner = wx.Rect(rect.x + EAR + 2, rect.y, rect.width - EAR * 2 - 4, rect.height)
        gc.SetPen(wx.Pen(wx.Colour(RACK['rail_edge']), 1, wx.PENSTYLE_SHORT_DASH))
        gc.SetBrush(wx.TRANSPARENT_BRUSH)
        gc.DrawRoundedRectangle(inner.x + 0.5, inner.y + 0.5, inner.width - 1,
                                inner.height - 1, 4)
        draw_text(gc, 'ADD A DEVICE', rect.x + EAR + INSET, rect.y + 9, 8.5, RACK['dim'],
                  bold=True)
        for button in self.buttons:
            button.draw(gc, FACES['master'][1])


class RackView(Canvas):

    def __init__(self, parent, theme, chain, power, on_change):
        super().__init__(parent, theme)
        self.on_change = on_change
        self.power = power
        self.state, self.folder = eapo.get_state()
        self.master = MasterUnit(self)
        self.slot = AddSlot(self)
        self.units = [build_unit(data, self) for data in chain]
        self.offset = 0
        self.total = 0
        self.active = None
        self.hovered = None
        self.thumb = None
        self.thumb_drag = None
        self.boost = None

        self.Bind(wx.EVT_LEFT_DOWN, self.on_down)
        self.Bind(wx.EVT_LEFT_DCLICK, self.on_dclick)
        self.Bind(wx.EVT_LEFT_UP, self.on_up)
        self.Bind(wx.EVT_MOTION, self.on_motion)
        self.Bind(wx.EVT_LEAVE_WINDOW, self.on_leave)
        self.Bind(wx.EVT_MOUSEWHEEL, self.on_wheel)
        self.Bind(wx.EVT_MOUSE_CAPTURE_LOST, self.on_capture_lost)
        self.Bind(wx.EVT_SIZE, lambda event: (self.clamp(), event.Skip()))

    # ------------------------------------------------------------ 자료

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
        # 이미 꽂아 둔 장치가 있으면 가져온 것을 그 위에 얹는다. 이어 붙이기 전의
        # 소리가 먼저 지나가고 랙이 그 뒤를 잇는다. 끊었다 다시 이으면 되돌려 놓았던
        # 줄을 또 가져오게 되므로, 랙에 이미 같은 줄이 있는 장치는 건너뛴다.
        # 플러그인은 값이 그 사이 바뀌었을 수 있어 파일 경로로 가린다.
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
        unit = build_unit(make_unit(kind), self)
        self.units.append(unit)
        # 고르다 그만두면 빈 칸을 남기지 않는다. 골랐는데 못 올렸으면 남겨 두어 까닭을 보인다.
        if kind == 'vst' and not unit.on_choose():
            self.units.remove(unit)
            self.Refresh()
            return
        self.on_unit_change()
        wx.CallAfter(self.reveal, unit)

    def remove(self, unit):
        if unit in self.units:
            if hasattr(unit, 'close'):
                unit.close()
            self.units.remove(unit)
            self.reset_pointer()
            self.on_unit_change()

    def move(self, unit, delta):
        index = self.units.index(unit)
        target = index + delta
        if 0 <= target < len(self.units):
            self.units[index], self.units[target] = self.units[target], self.units[index]
            self.on_unit_change()

    def close(self):
        for unit in self.units:
            if hasattr(unit, 'close'):
                unit.close()

    # ------------------------------------------------------------ 자리

    def get_blocks(self):
        return [self.master] + self.units + [self.slot]

    def get_controls(self):
        for block in self.get_blocks():
            for control in block.get_controls():
                yield control

    def layout(self, gc, width):
        y = MARGIN
        inner = width - MARGIN * 2
        for block in self.get_blocks():
            height = block.get_height(inner) if hasattr(block, 'get_height') else block.height
            block.layout(gc, wx.Rect(MARGIN, y, inner, height))
            y += block.rect.height + GAP
        self.total = y + MARGIN
        for control in self.get_controls():
            if isinstance(control, Button):
                control.on_reset = self.Refresh

    def get_room(self):
        return self.GetClientSize().height

    def clamp(self):
        self.offset = max(0, min(self.offset, self.total - self.get_room()))

    def reveal(self, unit):
        bottom = unit.rect.y + unit.rect.height + MARGIN + self.slot.height
        if bottom - self.offset > self.get_room():
            self.offset = bottom - self.get_room()
            self.clamp()
            self.Refresh()

    def draw(self, gc, width, height):
        rack_width = width - (SCROLLBAR + 4 if self.total > height else 0)
        self.layout(gc, rack_width)
        self.clamp()
        fill_rect(gc, RACK['bg'], 0, 0, width, height)
        gc.PushState()
        gc.Translate(0, -self.offset)
        draw_rails(gc, MARGIN, 0, rack_width - MARGIN * 2, max(self.total, self.offset + height),
                   EAR)
        for block in self.get_blocks():
            rect = block.rect
            if rect.y + rect.height < self.offset or rect.y > self.offset + height:
                continue
            block.draw(gc)
        gc.PopState()
        self.draw_scrollbar(gc, width, height)

    def draw_scrollbar(self, gc, width, height):
        self.thumb = None
        if self.total <= height:
            return
        size = max(SCROLL_MIN, height * height / self.total)
        top = (height - size) * self.offset / max(1, self.total - height)
        self.thumb = wx.Rect(width - SCROLLBAR - 2, round(top), SCROLLBAR, round(size))
        lit = self.thumb_drag is not None
        fill_rect(gc, RACK['rail_edge'] if not lit else RACK['faint'], self.thumb.x,
                  self.thumb.y + 2, self.thumb.width, self.thumb.height - 4, 4)

    # ------------------------------------------------------------ 마우스

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
        # 두 번 누름의 두 번째 누름은 누름으로 오지 않는다. 단추는 두 번째도 누름으로 친다.
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
        point = self.to_rack(position)
        if self.active is not None:
            self.active.on_drag(point, event.ShiftDown())
            return
        self.set_hover(self.find(point), point)

    def on_leave(self, event):
        if self.active is None:
            self.set_hover(None, wx.Point(-1, -1))

    def on_wheel(self, event):
        if self.active is not None:
            return
        self.offset -= event.GetWheelRotation() / max(1, event.GetWheelDelta()) * WHEEL_STEP
        self.clamp()
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
