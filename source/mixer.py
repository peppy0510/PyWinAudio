# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com

프로그램별 볼륨. Windows 볼륨 믹서와 같은 오디오 세션 API 를 쓴다 — 여기서 바꾼 값은
볼륨 믹서에도 그대로 보이고, 저쪽에서 바꾼 값도 다음 읽기에 이쪽으로 온다.

세션은 소리를 한 번이라도 낸 프로그램에만 생긴다. 한 프로그램이 세션을 여럿 만들면
(브라우저의 탭들) 이름으로 묶어 채널 하나로 다룬다.

COM 객체는 모두 주 스레드(wx 의 STA)에서 만들고 부른다.
'''


import ctypes
import os

from ctypes import wintypes


PYTHON_HOSTS = ('python.exe', 'pythonw.exe', 'py.exe', 'pyw.exe')
ENTRY_SCRIPTS = ('main.py', 'main.pyw', 'mainapp.py')
STATE_ACTIVE = 1
STATE_EXPIRED = 2
RENDER = 0
MULTIMEDIA = 1

shlwapi = ctypes.WinDLL('shlwapi')
shlwapi.SHLoadIndirectString.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.UINT,
                                         ctypes.c_void_p]


def resolve_indirect(text):
    ''''@%SystemRoot%\\System32\\AudioSrv.Dll,-202' 같은 리소스 글을 실제 글로.'''
    if not text or not text.startswith('@'):
        return text
    buffer = ctypes.create_unicode_buffer(512)
    if shlwapi.SHLoadIndirectString(os.path.expandvars(text), buffer, 512, None) == 0:
        return buffer.value
    return ''


def get_file_description(path):
    try:
        import win32api
        translations = win32api.GetFileVersionInfo(path, '\\VarFileInfo\\Translation')
        language, codepage = translations[0]
        key = '\\StringFileInfo\\%04x%04x\\FileDescription' % (language, codepage)
        return (win32api.GetFileVersionInfo(path, key) or '').strip()
    except Exception:
        return ''


def get_python_app(process):
    '''파이썬으로 띄운 앱은 모두 pythonw.exe 로 보인다. 실행한 스크립트에서 이름을 찾는다.
    PyWin 앱은 <프로젝트>/source/main.pyw 짜임이라 프로젝트 폴더 이름이 곧 앱 이름이다.'''
    try:
        arguments = process.cmdline()[1:]
        directory = process.cwd()
    except Exception:
        return None, None
    for argument in arguments:
        if argument.startswith('-'):
            continue
        script = os.path.abspath(os.path.join(directory, argument))
        folder, leaf = os.path.split(script)
        name = os.path.splitext(leaf)[0]
        project = folder
        if leaf.lower() in ENTRY_SCRIPTS:
            if os.path.basename(folder).lower() == 'source':
                project = os.path.dirname(folder)
            name = os.path.basename(project)
        icon = os.path.join(project, 'assets', 'icon', 'icon.ico')
        return name, icon if os.path.exists(icon) else None
    return None, None


class Channel:
    '''이름이 같은 세션들. 볼륨과 음소거는 묶인 세션 모두에 똑같이 건다.'''

    def __init__(self, key, name, icon):
        self.key = key
        self.name = name
        self.icon = icon
        self.sessions = []
        self.meters = []
        self.active = False

    def get_volume(self):
        try:
            return float(self.sessions[0].SimpleAudioVolume.GetMasterVolume())
        except Exception:
            return 0.0

    def set_volume(self, value):
        for session in self.sessions:
            try:
                session.SimpleAudioVolume.SetMasterVolume(float(value), None)
            except Exception:
                pass

    def get_mute(self):
        try:
            return bool(self.sessions[0].SimpleAudioVolume.GetMute())
        except Exception:
            return False

    def set_mute(self, value):
        for session in self.sessions:
            try:
                session.SimpleAudioVolume.SetMute(int(bool(value)), None)
            except Exception:
                pass

    def get_peak(self):
        '''소리를 내는(활성) 세션의 피크만 본다. 쉬는 세션의 미터는 마지막 값을 돌려주는
        일이 있어, 조용한 채널이 가끔 번쩍였다.'''
        peak = 0.0
        for session, meter in zip(self.sessions, self.meters):
            try:
                if session._ctl.GetState() != STATE_ACTIVE:
                    continue
                peak = max(peak, float(meter.GetPeakValue()))
            except Exception:
                pass
        return peak


class MasterChannel(Channel):
    '''출력 장치 전체. 끝점 볼륨과 끝점 피크를 쓴다.'''

    def __init__(self, name, endpoint, meter):
        super().__init__('master', name, None)
        self.endpoint = endpoint
        self.meter = meter
        self.active = True

    def get_volume(self):
        try:
            return float(self.endpoint.GetMasterVolumeLevelScalar())
        except Exception:
            return 0.0

    def set_volume(self, value):
        try:
            self.endpoint.SetMasterVolumeLevelScalar(float(value), None)
        except Exception:
            pass

    def get_mute(self):
        try:
            return bool(self.endpoint.GetMute())
        except Exception:
            return False

    def set_mute(self, value):
        try:
            self.endpoint.SetMute(int(bool(value)), None)
        except Exception:
            pass

    def get_peak(self):
        try:
            return float(self.meter.GetPeakValue())
        except Exception:
            return 0.0


class Mixer:

    def __init__(self):
        self.error = ''
        self.master = None
        self.channels = []
        self.device_id = None
        self.names = {}
        self.enumerator = None
        self.manager = None

    def refresh(self):
        '''세션 목록을 다시 읽는다. 채널 차례는 처음 나타난 차례를 지킨다 — 소리를 낼 때마다
        자리가 바뀌면 손이 갈 곳을 잃는다.

        pycaw 의 GetSpeakers 는 부를 때마다 장치 속성을 통째로 읽어 한 번에 40 ms 가 든다
        (GetAllSessions 도 안에서 한 번 더 부른다). 열거자와 세션 관리자는 쥐고 있다가 기본
        장치가 바뀔 때만 새로 만든다.'''
        try:
            import comtypes
            from pycaw.constants import CLSID_MMDeviceEnumerator
            from pycaw.pycaw import AudioSession
            from pycaw.pycaw import AudioUtilities
            from pycaw.pycaw import IAudioMeterInformation
            from pycaw.pycaw import IAudioSessionControl2
            from pycaw.pycaw import IAudioSessionManager2
            from pycaw.pycaw import IMMDeviceEnumerator
        except Exception as error:
            self.error = 'pycaw is not installed (%s)' % error
            return
        try:
            if self.enumerator is None:
                self.enumerator = comtypes.CoCreateInstance(
                    CLSID_MMDeviceEnumerator, IMMDeviceEnumerator, comtypes.CLSCTX_INPROC_SERVER)
            device = self.enumerator.GetDefaultAudioEndpoint(RENDER, MULTIMEDIA)
            device_id = device.GetId()
        except Exception as error:
            self.error = 'No output device' if self.master is None else str(error)
            self.master = None
            self.channels = []
            self.device_id = None
            return
        self.error = ''
        if self.master is None or device_id != self.device_id:
            self.device_id = device_id
            speakers = AudioUtilities.CreateDevice(device)
            meter = device.Activate(IAudioMeterInformation._iid_, comtypes.CLSCTX_ALL,
                                    None).QueryInterface(IAudioMeterInformation)
            self.master = MasterChannel(speakers.FriendlyName or 'Output', speakers.EndpointVolume,
                                        meter)
            self.manager = device.Activate(IAudioSessionManager2._iid_, comtypes.CLSCTX_ALL,
                                           None).QueryInterface(IAudioSessionManager2)
            self.channels = []

        order = {channel.key: index for index, channel in enumerate(self.channels)}
        found = {}
        sessions = self.manager.GetSessionEnumerator()
        for index in range(sessions.GetCount()):
            try:
                control = sessions.GetSession(index)
                if control is None:
                    continue
                session = AudioSession(control.QueryInterface(IAudioSessionControl2))
                if session.State == STATE_EXPIRED:
                    continue
                # 계기판의 루프백 받기가 이 프로세스에도 세션을 하나 만든다. 제 볼륨은 뺀다.
                if session.ProcessId == os.getpid():
                    continue
                key, name, icon = self.describe(session)
                channel = found.get(key)
                if channel is None:
                    channel = found[key] = Channel(key, name, icon)
                channel.sessions.append(session)
                channel.meters.append(session._ctl.QueryInterface(IAudioMeterInformation))
                channel.active = channel.active or session.State == 1
            except Exception:
                continue
        self.channels = sorted(found.values(),
                               key=lambda channel: order.get(channel.key, len(order)))

    def describe(self, session):
        process = session.Process
        if process is None:
            name = resolve_indirect(session.DisplayName) or 'System sounds'
            return 'system', name, None
        pid = process.pid
        if pid in self.names:
            return self.names[pid]
        try:
            path = process.exe()
        except Exception:
            path = ''
        executable = os.path.basename(path).lower() or process.name().lower()
        name = icon = None
        if executable in PYTHON_HOSTS:
            name, icon = get_python_app(process)
        if not name:
            name = (resolve_indirect(session.DisplayName) or get_file_description(path) or
                    os.path.splitext(executable)[0].capitalize())
        if icon is None and path:
            icon = path
        described = ('app:' + name.lower(), name, icon)
        self.names[pid] = described
        return described
