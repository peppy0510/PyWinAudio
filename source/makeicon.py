# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com

Draws assets/icon/icon.ico — one rack knob pointing straight up, its value arc lit
from the start to the centre. The other PyWin icons are one plain shape in two greys
on the dark disc; this keeps to that.
'''


import math
import os
import wx


SIZE = 128
DISC = '#2f333a'
TRACK = '#8b929b'
CAP = '#e6e9ed'

# 랙 손잡이와 같은 270 도 길. 바늘은 한가운데(12 시)를 가리킨다(사용자).
START = math.radians(135)
SWEEP = math.radians(270)
POINT = math.radians(270)


def draw_icon(gc, size):
    cx = cy = size / 2
    body = size * 0.24
    ring = body + size * 0.085
    line = size * 0.06

    def arc(start, end):
        path = gc.CreatePath()
        path.AddArc(cx, cy, ring, start, end, True)
        return path

    for colour, end in ((TRACK, START + SWEEP), (CAP, POINT)):
        gc.SetPen(gc.CreatePen(wx.GraphicsPenInfo(wx.Colour(colour)).Width(line)
                               .Cap(wx.CAP_ROUND)))
        gc.SetBrush(wx.TRANSPARENT_BRUSH)
        gc.StrokePath(arc(START, end))
    gc.SetPen(wx.TRANSPARENT_PEN)
    gc.SetBrush(wx.Brush(wx.Colour(TRACK)))
    gc.DrawEllipse(cx - body, cy - body, body * 2, body * 2)
    gc.SetPen(gc.CreatePen(wx.GraphicsPenInfo(wx.Colour(CAP)).Width(size * 0.055)
                           .Cap(wx.CAP_ROUND)))
    gc.StrokeLine(cx + math.cos(POINT) * body * 0.15, cy + math.sin(POINT) * body * 0.15,
                  cx + math.cos(POINT) * body * 0.75, cy + math.sin(POINT) * body * 0.75)


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
