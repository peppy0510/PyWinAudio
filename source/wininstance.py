# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com
'''


import ctypes


MUTEX_NAME = 'Local\\PyWinAudio'
ERROR_ALREADY_EXISTS = 183
SW_SHOW = 5
SW_RESTORE = 9

kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

# the mutex lives as long as this handle
handle = None


def has_running_instance():
    global handle
    handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if not handle:
        return False
    return ctypes.get_last_error() == ERROR_ALREADY_EXISTS


def show_running_window(title):
    # the running copy may sit hidden in the tray; bring it back instead of doing nothing
    user32 = ctypes.windll.user32
    hwnd = user32.FindWindowW('wxWindowNR', title)
    if not hwnd:
        return
    user32.ShowWindow(hwnd, SW_RESTORE if user32.IsIconic(hwnd) else SW_SHOW)
    user32.SetForegroundWindow(hwnd)
