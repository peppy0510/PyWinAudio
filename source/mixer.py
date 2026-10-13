# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com
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
    # python apps show as pythonw.exe; name them by the script's project folder
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
        # idle sessions can return a stale peak, so read active ones only
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


# COM objects live on the GUI thread (wx STA); create and call them there only
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
        # pycaw GetSpeakers reads every device property (40 ms); hold the enumerator and manager
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
                # the loopback capture makes a session for this process too
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
        # look the pid up first: pycaw's Process builds a psutil.Process on every refresh
        pid = session.ProcessId
        if pid in self.names:
            return self.names[pid]
        process = session.Process
        if process is None:
            name = resolve_indirect(session.DisplayName) or 'System sounds'
            return 'system', name, None
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
