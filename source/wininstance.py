# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com
'''


import ctypes


MUTEX_NAME = 'Local\\PyWinAudio'
ERROR_ALREADY_EXISTS = 183

kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

# the mutex lives as long as this handle
handle = None


def has_running_instance():
    global handle
    handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if not handle:
        return False
    return ctypes.get_last_error() == ERROR_ALREADY_EXISTS
