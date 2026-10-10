# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com

Draws assets/icon/icon.ico — two rack units, a knob on the top one and a lit
lamp beside it. A rack alone reads as a server; the knob says it is sound.
'''


import math
import os
import wx


SIZE = 128
DISC = '#1b1d21'
PANEL = '#3a3f46'
EDGE = '#5a5f67'
KNOB = '#e6e9ed'
LAMP = '#4c9aff'
ARC = '#ffb04d'


def draw_icon(gc, size):
    left, width = size * 0.12, size * 0.76
    for index, (top, height) in enumerate(((0.16, 0.40), (0.62, 0.22))):
        gc.SetPen(wx.TRANSPARENT_PEN)
        gc.SetBrush(wx.Brush(wx.Colour(PANEL)))
        gc.DrawRoundedRectangle(left, size * top, width, size * height, size * 0.05)
        gc.SetBrush(wx.Brush(wx.Colour(EDGE)))
        gc.DrawRectangle(left + size * 0.04, size * top, width - size * 0.08, size * 0.02)

    cx, cy, radius = size * 0.64, size * 0.36, size * 0.13
    gc.SetPen(gc.CreatePen(wx.GraphicsPenInfo(wx.Colour(ARC)).Width(size * 0.045)
                           .Cap(wx.CAP_ROUND)))
    gc.SetBrush(wx.TRANSPARENT_BRUSH)
    path = gc.CreatePath()
    path.AddArc(cx, cy, radius + size * 0.05, math.radians(135), math.radians(345), True)
    gc.StrokePath(path)
    gc.SetPen(wx.TRANSPARENT_PEN)
    gc.SetBrush(wx.Brush(wx.Colour(KNOB)))
    gc.DrawEllipse(cx - radius, cy - radius, radius * 2, radius * 2)
    gc.SetPen(gc.CreatePen(wx.GraphicsPenInfo(wx.Colour(DISC)).Width(size * 0.035)
                           .Cap(wx.CAP_ROUND)))
    angle = math.radians(345)
    gc.StrokeLine(cx, cy, cx + math.cos(angle) * radius * 0.8, cy + math.sin(angle) * radius * 0.8)

    gc.SetPen(wx.TRANSPARENT_PEN)
    gc.SetBrush(wx.Brush(wx.Colour(LAMP)))
    lamp = size * 0.055
    gc.DrawEllipse(size * 0.26 - lamp, cy - lamp, lamp * 2, lamp * 2)
    for index in range(3):
        x = size * 0.24 + index * size * 0.18
        gc.SetBrush(wx.Brush(wx.Colour(EDGE)))
        gc.DrawRoundedRectangle(x, size * 0.71, size * 0.12, size * 0.04, size * 0.02)


def main():
    app = wx.App(False)  # noqa
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, 'assets', 'icon')
    os.makedirs(path, exist_ok=True)

    bitmap = wx.Bitmap(SIZE, SIZE)
    dc = wx.MemoryDC(bitmap)
    dc.SetBackground(wx.Brush(wx.Colour(DISC)))
    dc.Clear()
    gc = wx.GraphicsContext.Create(dc)
    gc.SetAntialiasMode(wx.ANTIALIAS_DEFAULT)
    draw_icon(gc, SIZE)
    del gc
    dc.SelectObject(wx.NullBitmap)

    bitmap.SaveFile(os.path.join(path, 'icon.png'), wx.BITMAP_TYPE_PNG)
    bitmap.SaveFile(os.path.join(path, 'icon.ico'), wx.BITMAP_TYPE_ICO)
    print('[ ICON CREATED ] [ {} ]'.format(os.path.join(path, 'icon.ico')))


if __name__ == '__main__':
    main()
