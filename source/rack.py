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
from units import make_unit
from mixunit import MixerUnit
from utilities import Canvas


# 창 좌우·아래 여백. 14 는 넓어 보였다(사용자) — 스크롤바(폭 4 + 안쪽 3)가 들어갈 만큼만.
MARGIN = 8
GAP = 3
# 믹서 레벨을 다시 그리는 박자와 세션 목록을 다시 읽는 간격.
MIXER_FPS = 30
MIXER_REFRESH = 1000
MIXER_FALL = 15.0
WHEEL_STEP = 60
# 스크롤바는 평소에 숨는다. 굴리거나 끌 때, 오른쪽 여백에 손이 갈 때만 가는 막대로 뜬다.
# 색·모양은 PyWinAgent 의 막대 그대로(사용자): 폭 4, 모서리 2, 오른쪽 끝에서 3 안쪽, 어두운 테두리색.
SCROLLBAR = 4
SCROLLBAR_INSET = 3
SCROLLBAR_COLOUR = '#3a3f46'
SCROLL_MIN = 24
# 굴리고 나면 0.7 초 머문 뒤 0.4 초에 걸쳐 옅어진다 — 처음엔 빠르게, 끝에서 늦게(PyWinAgent 와 같다).
SCROLL_HOLD = 0.7
SCROLL_FADE = 0.4
SCROLL_STEP = 16


class MasterUnit:
    '''랙의 머리. 랙 전체를 켜고 끄고, Equalizer APO 와 이어졌는지 알린다. 이름 띠 한 줄뿐이다
    — 다른 장치의 띠와 같은 자리·같은 글씨.'''

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
        return os.path.join(self.rack.folder, eapo.OWN_FILE), RACK['dim']

    def draw(self, gc):
        rect = self.rect
        draw_faceplate(gc, rect.x, rect.y, rect.width, rect.height, self.face, EAR, self.accent)
        left = self.power.rect.x + 22
        right = self.text_right
        if self.rack.state == 'linked' and self.rack.power:
            # 계기판의 피크와 헷갈리지 않게, 이것은 EQ 들이 올리는 최대 이득이라고 부른다.
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
    '''비어 있는 랙 칸. 꽂을 장치를 고르는 단추가 줄지어 있다.'''

    height = U + 30

    def __init__(self, rack):
        self.rack = rack
        self.rect = wx.Rect()
        # 기본 장치는 메뉴 단추 하나로 묶고, VST 는 따로(사용자: 단추가 자리를 많이 차지한다).
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
    # 이름표와 단추를 한 줄에(사용자). 좁아서 안 들어가면 단추가 다음 줄로 내려간다.
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
        # 장치 판과 같은 좌우 끝에 선다. 안으로 들이면 랙과 끝이 어긋나 보인다.
        inner = rect
        gc.SetPen(wx.Pen(wx.Colour(RACK['line']), 1, wx.PENSTYLE_SHORT_DASH))
        gc.SetBrush(wx.TRANSPARENT_BRUSH)
        gc.DrawRoundedRectangle(inner.x + 0.5, inner.y + 0.5, inner.width - 1,
                                inner.height - 1, 4)
        draw_text(gc, self.LABEL, rect.x + EAR + INSET, self.label_y, self.LABEL_SIZE,
                  RACK['dim'], bold=True)
        for button in self.buttons:
            button.draw(gc, FACES['master'][1])


class RemoveConfirm:
    '''빼기 전에 그 장치 판 위에 덮는 물음. 무엇을 빼는지 이름으로 묻고, 단추 둘 가운데
    Remove 를 눌러야만 뺀다. 그 밖의 누름과 Esc 는 모두 그만두기다.'''

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
    '''정해진 박자로 믹서 레벨 한 장을 부탁한다. 앞 장을 다 그리기 전이면 건너뛴다.
    wx.Timer 는 15.6 ms 경계에 걸려 고르게 오지 않는다.'''

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
                    wx.CallAfter(self.view.tick)
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
        # 핀을 뺀 Analyzer 판이 앉을 자리. 신호 흐름대로 맨 아래(ADD 다음)에 비워 둔다(사용자).
        self.bottom_space = 0
        self.meters_y = 0
        # 맨 위 판 앞의 틈. 위에 핀 꽂은 Analyzer 가 있으면 장치 사이 GAP, 없으면 창 여백 MARGIN(주 창이 정한다).
        self.top_gap = MARGIN
        self.on_scroll = None
        self.notified = None
        self.scrolled_at = 0.0
        self.near_edge = False
        self.fade_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_scroll_fade, self.fade_timer)
        # WS_EX_COMPOSITED 를 켜 두면 믹서 레벨 한 칸만 다시 그리라고 해도 창 전체가 다시
        # 그려진다(실측: 한 코어 92 %). 버퍼는 AutoBufferedPaintDC 가 맡는다.
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
        self.cancel_remove()
        unit = build_unit(make_unit(kind), self)
        # VST 는 파일을 고른 뒤에야 칸을 꽂는다. 먼저 꽂으면 고르는 동안 빈 판이 랙에 보였다(사용자).
        # 그만두면 아무것도 남지 않고, 골랐는데 못 올렸으면 남겨 두어 까닭을 보인다.
        path = unit.pick_path() if kind == 'vst' else None
        if kind == 'vst' and path is None:
            return
        self.units.append(unit)
        if path is not None:
            unit.load(path)
        # Leveler 는 깔린 자리에서 바로 올린다. 깔려 있지 않으면 판에 까닭이 뜬다.
        if kind == 'leveler' and os.path.exists(unit.data['path']):
            unit.load(unit.data['path'])
        self.on_unit_change()
        wx.CallAfter(self.reveal, unit)

    def remove(self, unit):
        '''✕ 는 묻기만 한다. 빼는 것은 confirm_remove.'''
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
        '''물음을 거둔다. 거둘 것이 있었으면 참.'''
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
        # 접어 두었거나 다른 페이지에 있으면 목록을 읽지 않는다. 펼치는 순간 한 번 읽는다.
        if self.IsShownOnScreen() and not self.mixer.folded and self.mixer.refresh():
            self.Refresh()
        self.refresher = wx.CallLater(MIXER_REFRESH, self.refresh_mixer)

    def tick(self):
        '''믹서 레벨만 움직인다. 그 자리만 다시 그리게 해 나머지 장치는 건드리지 않는다.'''
        if not self:
            return
        self.pacer.pending = False
        now = time.perf_counter()
        elapsed = min(0.2, now - self.last_tick)
        self.last_tick = now
        if not self.IsShownOnScreen():
            return
        # Leveler 의 보정 계기는 세 번에 한 번(약 10 Hz)만 다시 칠한다.
        self.meter_ticks = getattr(self, 'meter_ticks', 0) + 1
        if self.meter_ticks % 3 == 0:
            room = self.get_room()
            for unit in self.units:
                rect = getattr(unit, 'meter_rect', None)
                if rect is None or unit.folded or not unit.update_meters(elapsed * 3):
                    continue
                box = wx.Rect(rect.x, rect.y - self.offset, rect.width, rect.height)
                if box.y + box.height >= 0 and box.y <= room:
                    self.RefreshRect(box.Inflate(2, 2), False)
        if self.mixer.folded:
            return
        changed = self.mixer.update_levels(elapsed, MIXER_FALL)
        # 판 전체가 아니라 켜진 칸 수가 바뀐 레벨 막대 자리만 다시 칠하게 한다. on_paint 가
        # 이 칸들만 걸린 칠하기를 알아보고 장치들을 다시 그리지 않고 막대만 얹는다.
        room = self.get_room()
        self.meter_boxes = []
        for column in self.mixer.columns:
            if column.channel.key not in changed:
                continue
            meter = column.meter
            box = wx.Rect(meter.x, meter.y - self.offset, meter.width, meter.height)
            if box.y + box.height < 0 or box.y > room:
                continue
            self.meter_boxes.append(box)
            self.RefreshRect(box, False)

    def close(self):
        self.pacer.running = False
        self.fade_timer.Stop()
        if self.refresher is not None and self.refresher.IsRunning():
            self.refresher.Stop()
        for unit in self.units:
            if hasattr(unit, 'close'):
                unit.close()

    # ------------------------------------------------------------ 자리

    def get_blocks(self):
        # 신호 흐름 순: 앱 볼륨(Mixer) → 체인 전원 띠 → 장치들 → ADD(사용자). 전원 띠가 Mixer 위에
        # 있으면 Mixer 까지 끄는 것처럼 보였다.
        return [self.mixer, self.master] + self.units + [self.slot]

    def get_controls(self):
        # 묻는 동안 그 장치의 손잡이는 덮개 아래에 있다. 덮개 단추만 받는다.
        if self.confirm is not None:
            for control in self.confirm.get_controls():
                yield control
        for block in self.get_blocks():
            if self.confirm is not None and block is self.confirm.unit:
                continue
            for control in block.get_controls():
                yield control

    def layout(self, gc, width):
        y = self.top_gap
        inner = width - MARGIN * 2
        for block in self.get_blocks():
            height = block.get_height(inner) if hasattr(block, 'get_height') else block.height
            block.layout(gc, wx.Rect(MARGIN, y, inner, height))
            y += block.rect.height + GAP
        # 아래 Analyzer 판과는 장치 사이와 같은 간격만 둔다. 레일만 보이는 틈을 남기지 않는다.
        self.meters_y = y
        # 맨 아래 여백은 좌우와 같은 MARGIN 하나. 마지막 판 뒤의 GAP 까지 더하면 3 화소 넓었다(사용자).
        self.total = (y + self.bottom_space if self.bottom_space else y - GAP) + MARGIN
        if self.confirm is not None:
            self.confirm.layout(gc)
        for control in self.get_controls():
            if isinstance(control, Button):
                control.on_reset = self.Refresh

    def get_room(self):
        return self.GetClientSize().height

    def clamp(self):
        # 휠·스크롤바 끌기 셈은 실수가 나온다. wx.Point·wx.Rect 는 실수를 거절해서, 한 번 실수가
        # 되면 마우스 찾기·그리기가 줄줄이 죽는다(핀을 뺀 Analyzer 판도 따라오지 못했다).
        self.offset = int(round(max(0, min(self.offset, self.total - self.get_room()))))

    def reveal(self, unit):
        bottom = unit.rect.y + unit.rect.height + MARGIN + self.slot.height
        if bottom - self.offset > self.get_room():
            self.offset = bottom - self.get_room()
            self.clamp()
            self.Refresh()

    def draw(self, gc, width, height):
        # 스크롤바는 오른쪽 여백 안에 겹쳐 그린다. 생길 때마다 랙 폭이 줄면 위 계기판과
        # 끝이 어긋나고 장치들이 옆으로 밀려 보인다.
        rack_width = width
        self.layout(gc, rack_width)
        self.clamp()
        # 굴렀거나 장치가 늘고 줄어 아래 Analyzer 자리가 바뀌면 판을 옮기게 알린다.
        if self.on_scroll is not None and self.notified != (self.offset, self.meters_y):
            self.notified = (self.offset, self.meters_y)
            wx.CallAfter(self.on_scroll)
        fill_rect(gc, RACK['bg'], 0, 0, width, height)
        gc.PushState()
        gc.Translate(0, -self.offset)
        draw_rails(gc, MARGIN, 0, rack_width - MARGIN * 2, max(self.total, self.offset + height),
                   EAR)
        # 다시 그릴 곳이 일부뿐이면(믹서 레벨) 거기 걸친 장치만 그린다. 곡선을 다시 셈하는
        # EQ 들까지 30 장마다 그리면 무겁다.
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
        box = self.GetUpdateRegion().GetBox()
        boxes, self.meter_boxes = self.meter_boxes, []
        if boxes and self.is_meter_only(box, boxes):
            dc = wx.PaintDC(self)
            self.mixer.paint_levels(dc, self.offset, box)
            return
        self.update_box = box
        super().on_paint(event)
        self.update_box = None

    def is_meter_only(self, box, boxes):
        '''칠할 곳이 레벨 막대들을 묶은 줄 안에만 있으면 참. 손잡이 위에 손이 올라간 것처럼
        다른 곳도 함께 칠해야 하면 거짓 — 그때는 평소처럼 다 그린다.'''
        union = wx.Rect(boxes[0])
        for meter in boxes[1:]:
            union = union.Union(meter)
        return union.Contains(box)

    def draw_scrollbar(self, gc, width, height):
        self.thumb = None
        if self.total <= height:
            return
        size = max(SCROLL_MIN, height * height / self.total)
        top = (height - size) * self.offset / max(1, self.total - height)
        # 잡는 자리는 오른쪽 여백 전체. 그리는 막대만 가늘다.
        self.thumb = wx.Rect(width - MARGIN, round(top), MARGIN, round(size))
        alpha = self.get_scroll_alpha()
        if alpha <= 0:
            return
        tone = wx.Colour(SCROLLBAR_COLOUR)
        fill_rect(gc, wx.Colour(tone.Red(), tone.Green(), tone.Blue(), int(255 * alpha)),
                  width - SCROLLBAR_INSET - SCROLLBAR, self.thumb.y, SCROLLBAR, self.thumb.height, 2)

    def get_scroll_alpha(self):
        '''끌거나 오른쪽 여백에 손이 있으면 다 보이고, 그 밖에는 굴린 뒤 머물렀다가 옅어진다.'''
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
        # 옅어지는 동안은 막대 자리만 다시 그린다. 판 전체를 60 번 그리면 무겁다.
        self.RefreshRect(wx.Rect(width - MARGIN, 0, MARGIN, height), False)
        if self.get_scroll_alpha() <= 0:
            self.fade_timer.Stop()

    def show_scrollbar(self):
        '''굴린 뒤 잠깐 보이고 다시 숨는다. 숨길 때 한 번 더 그린다.'''
        self.scrolled_at = time.perf_counter()
        if not self.fade_timer.IsRunning():
            self.fade_timer.Start(SCROLL_STEP)

    def set_near_edge(self, near):
        if near != self.near_edge:
            self.near_edge = near
            if near:
                self.Refresh()
            else:
                # 손이 떠나면 곧장 지우지 않고 굴린 뒤처럼 머물렀다 옅어진다.
                self.show_scrollbar()

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
        # 물음 밖을 누르면 그만둔다. 그 누름은 덮개가 걷힌 자리에 그대로 간다.
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
        # 휠은 언제나 랙을 굴린다. 믹서 페이더도 휠로는 움직이지 않는다 — 굴리다 지나가는
        # 페이더가 볼륨을 바꿔 버렸다(사용자 지적으로 되돌림).
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
