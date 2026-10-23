# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com
'''


import os
import sys

from wininstance import has_running_instance
from wininstance import show_running_window


# OpenBLAS commits a buffer per core as numpy loads (750 MB on 32 threads)
os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')


class stderr:
    def write(self, *args, **kwargs):
        pass

    # without flush, pythonw exits with code 120
    def flush(self, *args, **kwargs):
        pass


# pythonw leaves the standard streams as None
if not sys.stderr:
    sys.stderr = stderr()
if not sys.stdout:
    sys.stdout = stderr()


def launch():
    from mainapp import launch_mainapp
    launch_mainapp()


def main():
    if has_running_instance():
        print('PyWinAudio is already running.')
        show_running_window('PyWinAudio')
        return
    launch()


if __name__ == '__main__':
    main()
