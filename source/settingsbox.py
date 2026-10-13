# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com
'''


import ctypes
import makeshortcut
import os
import wx

import eapo

from controls import ButtonCard
from controls import NoticeCard
from controls import SettingCard
from shortcut import ShortCut
from utilities import APP_NAME
from utilities import get_font


MARGIN = 16
TITLE_INSET = 3
TITLE_GAP = 8
CARD_GAP = 4
GROUP_GAP = 14
CONFIRM_DELAY = 4000


class SettingsBox(wx.Panel):

    def __init__(self, parent, theme, settings, on_change, on_unlink):
        super().__init__(parent)
        self.on_unlink = on_unlink
        self.asking = None
        self.ontop = SettingCard(self, theme, 'Always on top',
                                 'Keep the window above others', on_change)
        self.dark = SettingCard(self, theme, 'Dark theme',
                                'Use the dark colour scheme for the window', on_change)
        self.wide = SettingCard(self, theme, 'Wide layout',
                                'Lay the rack out in columns when the window is wide', on_change)
        self.status = NoticeCard(self, theme, 'Equalizer APO', '')
        self.devices = ButtonCard(self, theme, 'Devices',
                                  'Pick the outputs Equalizer APO processes',
                                  'Choose', self.on_devices)
        self.folder = ButtonCard(self, theme, 'Config folder',
                                 'Where the rack is written', 'Open', self.on_folder)
        self.unlink = ButtonCard(self, theme, 'Unlink',
                                 'Put the previous config.txt back', 'Unlink',
                                 self.on_unlink_click)
        self.shortcut = ButtonCard(self, theme, 'Start menu',
                                   'Put a shortcut in the Start menu',
                                   'Create', self.on_shortcut)
        self.cards = (self.ontop, self.dark, self.wide, self.status, self.devices, self.folder,
                      self.unlink, self.shortcut)

        self.ontop.SetValue(settings.get('on_top', False))
        self.dark.SetValue(settings.get('theme', 'dark') == 'dark')
        self.wide.SetValue(settings.get('wide_layout', True))

        self.groups = []
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.AddSpacer(MARGIN)
        for title, cards in (('Window', (self.ontop, self.dark, self.wide)),
                             ('Equalizer APO', (self.status, self.devices, self.folder,
                                                self.unlink)),
                             ('Shortcut', (self.shortcut,))):
            label = wx.StaticText(self, label=title)
            label.SetFont(get_font(10, bold=True))
            self.groups.append(label)
            sizer.Add(label, 0, wx.LEFT, MARGIN + TITLE_INSET)
            sizer.AddSpacer(TITLE_GAP)
            for index, card in enumerate(cards):
                if index:
                    sizer.AddSpacer(CARD_GAP)
                sizer.Add(card, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, MARGIN)
            sizer.AddSpacer(GROUP_GAP)
        sizer.AddStretchSpacer()
        self.SetSizer(sizer)
        self.apply_theme(theme)
        self.refresh_state()

    def refresh_state(self):
        state, folder = eapo.get_state()
        if state == 'missing':
            self.status.set_label('Equalizer APO', 'Not installed, or its config folder is missing')
            self.status.set_tone('warn')
        elif state == 'unlinked':
            self.status.set_label('Equalizer APO', 'Installed, not linked yet. Link it from the rack')
            self.status.set_tone('warn')
        else:
            self.status.set_label('Equalizer APO', 'Linked, the rack is in %s' % eapo.OWN_FILE)
            self.status.set_tone('done')
        self.devices.set_enabled(eapo.get_device_selector() is not None)
        self.folder.set_enabled(folder is not None)
        self.unlink.set_enabled(state == 'linked')

    def on_devices(self):
        # DeviceSelector writes HKLM, so it runs elevated
        path = eapo.get_device_selector()
        if not path:
            return
        try:
            ctypes.windll.shell32.ShellExecuteW(None, 'runas', path, None,
                                                os.path.dirname(path), 1)
        except Exception:
            pass

    def on_folder(self):
        folder = eapo.get_config_path()
        if folder:
            os.startfile(folder)

    def on_unlink_click(self):
        if self.asking is None:
            self.unlink.set_caption('Unlink?')
            self.unlink.set_tone('warn')
            self.asking = wx.CallLater(CONFIRM_DELAY, self.reset_unlink)
            return
        self.reset_unlink()
        self.on_unlink()
        self.refresh_state()

    def reset_unlink(self):
        if self.asking is not None and self.asking.IsRunning():
            self.asking.Stop()
        self.asking = None
        self.unlink.set_caption('Unlink')
        self.unlink.set_tone('dim')

    def on_shortcut(self):
        try:
            makeshortcut.create(ShortCut.get_user_programs_path(APP_NAME))
        except Exception:
            self.shortcut.set_label('Start menu', 'Could not create the shortcut')
            self.shortcut.set_tone('warn')
            return
        self.shortcut.set_label('Start menu', 'Shortcut created')
        self.shortcut.set_tone('done')

    def apply_theme(self, theme):
        self.SetBackgroundColour(wx.Colour(theme['bg']))
        for label in self.groups:
            label.SetForegroundColour(wx.Colour(theme['text']))
        for card in self.cards:
            card.set_theme(theme)
        self.Refresh()
