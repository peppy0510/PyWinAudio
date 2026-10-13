# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com
'''


import math
import wx

from utilities import CARD_HEIGHT
from utilities import CARD_RADIUS
from utilities import Canvas
from utilities import draw_card_rim
from utilities import get_font
from utilities import mix
from utilities import shade


class Pressable(Canvas):

    def __init__(self, parent, theme, on_click):
        super().__init__(parent, theme)
        self.on_click = on_click
        self.hovered = False
        self.pressed = False
        self.Bind(wx.EVT_LEFT_DOWN, self.on_down)
        self.Bind(wx.EVT_LEFT_UP, self.on_up)
        self.Bind(wx.EVT_ENTER_WINDOW, self.on_enter)
        self.Bind(wx.EVT_LEAVE_WINDOW, self.on_leave)

    def on_down(self, event):
        self.pressed = True
        self.Refresh()

    def on_up(self, event):
        was_pressed = self.pressed
        self.pressed = False
        self.Refresh()
        if was_pressed and self.hovered and self.on_click:
            self.on_click()

    def on_enter(self, event):
        self.hovered = True
        self.Refresh()

    def on_leave(self, event):
        self.hovered = False
        self.pressed = False
        self.Refresh()


class CardBase(Pressable):

    PADDING = 14
    LABEL_GAP = 12
    # cards that change nothing on press do not light on hover
    reactive = True
    tone = 'dim'

    def __init__(self, parent, theme, label, description, on_change=None):
        super().__init__(parent, theme, self.activate)
        self.label = label
        self.description = description
        self.on_change = on_change
        self.SetMinSize(wx.Size(-1, CARD_HEIGHT))

    def activate(self):
        pass

    def notify(self):
        self.Refresh()
        if self.on_change:
            self.on_change()

    def set_label(self, label, description):
        self.label = label
        self.description = description
        self.Refresh()

    def set_tone(self, tone):
        self.tone = tone
        self.Refresh()

    def get_fill(self):
        fill = self.theme['face']
        if not self.reactive:
            return fill
        if self.pressed:
            return shade(fill, 0.94)
        if self.hovered:
            return shade(fill, 1.12)
        return fill

    def draw(self, gc, width, height):
        theme = self.theme
        gc.SetPen(wx.TRANSPARENT_PEN)
        gc.SetBrush(wx.Brush(wx.Colour(self.get_fill())))
        gc.DrawRoundedRectangle(0, 0, width, height, CARD_RADIUS)
        draw_card_rim(gc, theme['rim'], 0, 0, width, height)

        label_right = self.draw_control(gc, width, height) - self.LABEL_GAP
        self.draw_label(gc, height, self.PADDING,
                        max(0, label_right - self.PADDING))

    def draw_label(self, gc, height, left, limit):
        theme = self.theme
        gc.SetFont(get_font(10), wx.Colour(theme['text']))
        title_height = gc.GetTextExtent(self.label)[1]
        top = (height - title_height - 15) / 2
        gc.DrawText(self.fit_text(gc, self.label, limit), left, top)
        gc.SetFont(get_font(8), wx.Colour(self.get_description_colour()))
        gc.DrawText(self.fit_description(gc, self.description, limit), left,
                    top + title_height + 1)

    def fit_description(self, gc, text, limit):
        return self.fit_text(gc, text, limit)

    def get_description_colour(self):
        return self.theme[self.tone]

    def draw_control(self, gc, width, height):
        return width - self.PADDING


class NoticeCard(CardBase):

    reactive = False

    def __init__(self, parent, theme, label, description, tone='dim'):
        super().__init__(parent, theme, label, description)
        self.tone = tone


class SettingCard(CardBase):

    TRACK_WIDTH = 38
    TRACK_HEIGHT = 20

    value = False

    def GetValue(self):
        return self.value

    def SetValue(self, value):
        self.value = bool(value)
        self.Refresh()

    def activate(self):
        self.value = not self.value
        self.notify()

    def draw_control(self, gc, width, height):
        theme = self.theme
        switch_left = width - self.PADDING - self.TRACK_WIDTH
        state = 'On' if self.value else 'Off'
        gc.SetFont(get_font(9), wx.Colour(theme['dim']))
        state_width, state_height = gc.GetTextExtent(state)[:2]
        gc.DrawText(state, switch_left - state_width - 8, (height - state_height) / 2)
        # a half-pixel top blurs the pill edges
        self.draw_switch(gc, switch_left, round((height - self.TRACK_HEIGHT) / 2))
        return switch_left - state_width - 8

    def draw_switch(self, gc, left, top):
        theme = self.theme
        radius = self.TRACK_HEIGHT / 2
        gc.SetPen(wx.TRANSPARENT_PEN)

        # a stroked rim straddles pixels, so fill a 1px smaller pill over a full one
        if self.value:
            gc.SetBrush(wx.Brush(wx.Colour(theme['accent'])))
            gc.FillPath(self.get_track(gc, left, top, 0))
        else:
            gc.SetBrush(wx.Brush(wx.Colour(theme['dim'])))
            gc.FillPath(self.get_track(gc, left, top, 0))
            gc.SetBrush(wx.Brush(wx.Colour(theme['bg'])))
            gc.FillPath(self.get_track(gc, left, top, 1))

        knob = radius - 4
        x = left + (self.TRACK_WIDTH - radius if self.value else radius)
        gc.SetBrush(wx.Brush(wx.Colour('#ffffff' if self.value else theme['text'])))
        gc.DrawEllipse(x - knob, top + radius - knob, knob * 2, knob * 2)

    def get_track(self, gc, left, top, inset):
        # rounded rectangles kink where arc meets line when radius is half the height
        left, top = left + inset, top + inset
        width, height = self.TRACK_WIDTH - inset * 2, self.TRACK_HEIGHT - inset * 2
        radius = height / 2

        path = gc.CreatePath()
        path.MoveToPoint(left + radius, top)
        path.AddLineToPoint(left + width - radius, top)
        path.AddArc(left + width - radius, top + radius, radius,
                    -math.pi / 2, math.pi / 2, True)
        path.AddLineToPoint(left + radius, top + height)
        path.AddArc(left + radius, top + radius, radius, math.pi / 2, -math.pi / 2, True)
        path.CloseSubpath()
        return path


class ButtonCard(CardBase):

    BUTTON_HEIGHT = 26
    BUTTON_PADDING = 16
    BUTTON_RADIUS = 5

    def __init__(self, parent, theme, label, description, caption, on_click):
        super().__init__(parent, theme, label, description)
        self.action = on_click
        self.enabled = True
        self.set_caption(caption)

    def set_caption(self, caption):
        self.caption = caption
        dc = wx.MemoryDC(wx.Bitmap(1, 1))
        dc.SetFont(get_font(9))
        self.button = dc.GetTextExtent(caption)[0] + self.BUTTON_PADDING * 2
        self.Refresh()

    def set_enabled(self, enabled):
        self.enabled = enabled
        self.Refresh()

    def get_button_rect(self):
        width, height = self.GetClientSize()
        return wx.Rect(width - self.PADDING - self.button,
                       round((height - self.BUTTON_HEIGHT) / 2),
                       self.button, self.BUTTON_HEIGHT)

    def activate(self):
        if not self.enabled:
            return
        if self.get_button_rect().Contains(self.ScreenToClient(wx.GetMousePosition())):
            self.action()

    def draw_control(self, gc, width, height):
        theme = self.theme
        rect = self.get_button_rect()
        fill = theme['control']
        if not self.enabled:
            fill = mix(theme['face'], theme['control'], 0.5)
        elif self.pressed:
            fill = shade(fill, 0.90)
        elif self.hovered:
            fill = mix(theme['control'], theme['text'], 0.14)

        gc.SetPen(wx.TRANSPARENT_PEN)
        gc.SetBrush(wx.Brush(wx.Colour(fill)))
        gc.DrawRoundedRectangle(rect.x, rect.y, rect.width, rect.height,
                                self.BUTTON_RADIUS)
        gc.SetFont(get_font(9), wx.Colour(theme['text' if self.enabled else 'dim']))
        text_width, text_height = gc.GetTextExtent(self.caption)[:2]
        gc.DrawText(self.caption, rect.x + (rect.width - text_width) / 2,
                    rect.y + (rect.height - text_height) / 2)
        return rect.x


class TextCard(CardBase):
    # the native border ignores the theme, so it is drawn here

    reactive = False
    editable = True
    # auto names often overflow a fixed width
    FIELD_MIN = 200
    FIELD_RATIO = 0.52
    FIELD_HEIGHT = 26
    FIELD_INSET = 8
    FIELD_RADIUS = 5

    def __init__(self, parent, theme, label, description, hint, on_change=None):
        super().__init__(parent, theme, label, description, on_change)
        self.field = wx.TextCtrl(self, style=wx.BORDER_NONE)
        self.field.SetHint(hint)
        self.field.SetFont(get_font(10))
        self.field.Bind(wx.EVT_TEXT, self.on_text)
        self.Bind(wx.EVT_SIZE, self.on_size)

    def GetValue(self):
        return self.field.GetValue().strip()

    def SetValue(self, value):
        self.field.ChangeValue(value)

    def on_text(self, event):
        if self.on_change:
            self.on_change()
        event.Skip()

    def get_field_rect(self):
        width, height = self.GetClientSize()
        field = max(self.FIELD_MIN, round(width * self.FIELD_RATIO))
        return wx.Rect(width - self.PADDING - field,
                       round((height - self.FIELD_HEIGHT) / 2),
                       field, self.FIELD_HEIGHT)

    def on_size(self, event):
        rect = self.get_field_rect()
        text_height = self.field.GetBestSize().height
        self.field.SetSize(rect.x + self.FIELD_INSET,
                           rect.y + round((rect.height - text_height) / 2),
                           rect.width - self.FIELD_INSET * 2, text_height)
        event.Skip()

    def set_editable(self, editable):
        self.editable = editable
        self.field.SetEditable(editable)
        self.paint_field()

    def paint_field(self):
        theme = self.theme
        self.field.SetBackgroundColour(wx.Colour(theme['control']))
        self.field.SetForegroundColour(
            wx.Colour(theme['text'] if self.editable else theme['dim']))
        self.field.Refresh()

    def set_theme(self, theme):
        super().set_theme(theme)
        self.paint_field()

    def draw_control(self, gc, width, height):
        rect = self.get_field_rect()
        gc.SetPen(wx.TRANSPARENT_PEN)
        gc.SetBrush(wx.Brush(wx.Colour(self.theme['control'])))
        gc.DrawRoundedRectangle(rect.x, rect.y, rect.width, rect.height,
                                self.FIELD_RADIUS)
        return rect.x


class PathCard(ButtonCard):
    # cut from the left: the leaf is what changes

    def fit_description(self, gc, text, limit):
        return self.fit_tail(gc, text, limit)
