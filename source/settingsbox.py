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
from controls import ChoiceCard
from controls import NoticeCard
from controls import Panel
from controls import ScrollArea
from controls import SettingCard
from shortcut import ShortCut
from utilities import APP_NAME


CONFIRM_DELAY = 4000
THEMES = (('auto', 'Auto'), ('light', 'Light'), ('dark', 'Dark'))
ACCENTS = (('blue', 'Blue'), ('red', 'Red'))


class SettingsBox(ScrollArea):

    def __init__(self, parent, theme, settings, on_change, on_unlink, folds=None,
                 on_fold=None):
        super().__init__(parent, theme)
        self.on_unlink = on_unlink
        self.asking = None
        self.folds = folds if folds is not None else set()
        self.on_folds = on_fold
        board = self.content

        def toggle(label, description):
            return SettingCard(board, theme, label, description, on_change)

        self.ontop = toggle('Always on top', 'Keep the window above others')
        self.tray = toggle('Tray icon', 'Show an icon in the notification area')
        self.close_to_tray = toggle('Close to tray',
                                    'Closing hides the window instead of quitting')
        self.theme_choice = ChoiceCard(board, theme, 'Theme', 'Auto follows Windows', THEMES,
                                       on_change)
        self.accent_choice = ChoiceCard(board, theme, 'Accent',
                                        'Buttons on, the rack\'s keys and the menu', ACCENTS,
                                        on_change)
        self.wide = toggle('Wide layout', 'Lay the rack out in columns when the window is wide')
        self.status = NoticeCard(board, theme, 'Equalizer APO', '')
        self.devices = ButtonCard(board, theme, 'Devices',
                                  'Pick the outputs Equalizer APO processes', 'Choose',
                                  self.on_devices)
        self.folder = ButtonCard(board, theme, 'Config folder', 'Where the rack is written',
                                 'Open', self.on_folder)
        self.unlink = ButtonCard(board, theme, 'Unlink', 'Put the previous config.txt back',
                                 'Unlink', self.on_unlink_click)
        self.unlink.set_captions('Unlink?')
        self.shortcut = ButtonCard(board, theme, 'Start menu', 'Put a shortcut in the Start menu',
                                   'Create', self.on_shortcut)

        self.ontop.SetValue(settings.get('on_top', False))
        self.tray.SetValue(settings.get('tray_icon', True))
        self.close_to_tray.SetValue(settings.get('close_to_tray', False))
        self.theme_choice.SetValue(settings.get('theme', 'dark'))
        self.accent_choice.SetValue(settings.get('accent', 'blue'))
        self.wide.SetValue(settings.get('wide_layout', True))

        self.set_panels([
            Panel(board, theme, 'settings.window', 'Window',
                  (self.ontop, self.tray, self.close_to_tray), self.folds, self.on_fold),
            Panel(board, theme, 'settings.appearance', 'Appearance',
                  (self.theme_choice, self.accent_choice, self.wide), self.folds,
                  self.on_fold),
            Panel(board, theme, 'settings.eapo', 'Equalizer APO',
                  (self.status, self.devices, self.folder, self.unlink), self.folds,
                  self.on_fold),
            Panel(board, theme, 'settings.shortcut', 'Shortcut', (self.shortcut,), self.folds,
                  self.on_fold),
        ])
        self.bind_children()
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
            self.status.set_label('Equalizer APO', f'Linked, the rack is in {eapo.OWN_FILE}')
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
        self.unlink.set_tone('plain')

    def on_shortcut(self):
        try:
            makeshortcut.create(ShortCut.get_user_programs_path(APP_NAME))
        except Exception:
            self.shortcut.set_label('Start menu', 'Could not create the shortcut')
            self.shortcut.set_tone('warn')
            return
        self.shortcut.set_label('Start menu', 'Shortcut created')
        self.shortcut.set_tone('done')

    def on_fold(self):
        self.relayout_panels()
        if self.on_folds:
            self.on_folds()

    def apply_theme(self, theme):
        self.set_theme(theme)
        for child in self.content.GetChildren():
            if hasattr(child, 'set_theme'):
                child.set_theme(theme)
        self.Refresh()
