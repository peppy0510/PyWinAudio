# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com
'''


import ctypes


MUTEX_NAME = 'Local\\PyWinAudio'
ERROR_ALREADY_EXISTS = 183

kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

# The mutex lives as long as this handle does, so the process has to keep it.
handle = None


def has_running_instance():
    '''Walking the process list cannot do this job here. The app relaunches itself
    elevated, so the two sides sit at different integrity levels and psutil is
    refused the command line it would have to read; and a run started as
    `python .\\source\\main.pyw` carries a relative path that matches nothing.'''
    global handle
    handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if not handle:
        return False
    return ctypes.get_last_error() == ERROR_ALREADY_EXISTS
