# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com

Draws assets/icon/icon.ico — three faders set at different heights. The other
PyWin icons are one plain shape in two greys on the dark disc; this keeps to that.
'''


import os
import wx


SIZE = 128
DISC = '#2f333a'
TRACK = '#8b929b'
CAP = '#e6e9ed'

# 가로 자리와 손잡이 높이(위에서부터의 비율). 가운데가 내려가 EQ 곡선으로 읽힌다.
FADERS = ((0.27, 0.36), (0.50, 0.62), (0.73, 0.30))


def draw_icon(gc, size):
    top, bottom = size * 0.20, size * 0.80
    track = size * 0.055
    width, height = size * 0.20, size * 0.11
    gc.SetPen(wx.TRANSPARENT_PEN)
    for x, ratio in FADERS:
        cx = size * x
        gc.SetBrush(wx.Brush(wx.Colour(TRACK)))
        gc.DrawRoundedRectangle(cx - track / 2, top, track, bottom - top, track / 2)
        cy = size * ratio
        gc.SetBrush(wx.Brush(wx.Colour(CAP)))
        gc.DrawRoundedRectangle(cx - width / 2, cy - height / 2, width, height, height * 0.3)


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
