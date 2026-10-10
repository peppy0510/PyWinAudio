# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com
'''


import sys

from wininstance import has_running_instance


class stderr:
    def write(self, *args, **kwargs):
        pass

    # 없으면 종료할 때 파이썬이 스트림을 못 비워 exit code 120 으로 끝난다.
    def flush(self, *args, **kwargs):
        pass


# pythonw 로 띄우면 표준 스트림이 셋 다 None 이라 print 한 줄에 죽는다.
if not sys.stderr:
    sys.stderr = stderr()
if not sys.stdout:
    sys.stdout = stderr()


def launch():
    from mainapp import launch_mainapp
    launch_mainapp()


def main():
    # Equalizer APO 의 config 폴더는 Users 에게 쓰기가 열려 있다. 승격하지 않는다.
    if has_running_instance():
        print('PyWinAudio is already running.')
        return
    launch()


if __name__ == '__main__':
    main()
