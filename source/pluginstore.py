# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com
'''


import os
import re
import shutil
import subprocess
import tempfile
import zipfile

import vsthost


# shared by the whole PC: audiodg (LocalService) cannot read anything under a user profile
STORE = os.path.join(os.environ.get('PROGRAMDATA', r'C:\ProgramData'), 'PyWinAudio', 'vstplugins')
LOCAL_SERVICE = '*S-1-5-19'


def ensure_store():
    if not os.path.isdir(STORE):
        os.makedirs(STORE)
        # Users read is inherited from ProgramData; say LocalService outright so a reset ACL cannot drop it
        subprocess.run(['icacls', STORE, '/grant', LOCAL_SERVICE + ':(OI)(CI)RX'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       creationflags=subprocess.CREATE_NO_WINDOW)
    return STORE


def get_slug(text):
    return re.sub(r'[^0-9A-Za-z._-]+', '_', text).strip('._') or 'plugin'


def install_zip(path):
    # every version gets its own folder: the engine keeps the old DLL open until it reloads
    ensure_store()
    with zipfile.ZipFile(path) as archive:
        names = [name for name in archive.namelist() if not name.endswith('/')]
        scratch = tempfile.mkdtemp(prefix='pywinaudio-')
        try:
            found = None
            # the 64-bit VST2 in the archive; 32-bit twins and VST3 bundles are skipped
            for name in names:
                if not name.lower().endswith('.dll') or '.vst3/' in name.lower():
                    continue
                target = os.path.join(scratch, 'probe.dll')
                with archive.open(name) as source, open(target, 'wb') as file:
                    shutil.copyfileobj(source, file)
                if vsthost.get_bitness(target) == 64:
                    found = name
                    break
        finally:
            shutil.rmtree(scratch, ignore_errors=True)
        if found is None:
            raise ValueError('No 64-bit VST2 plugin in this archive')
        base = os.path.splitext(os.path.basename(found))[0]
        folder = os.path.join(STORE, get_slug(base), get_slug(os.path.splitext(os.path.basename(path))[0]))
        if os.path.isdir(folder):
            folder = get_free_folder(folder)
        os.makedirs(folder)
        # the plugin's own folder comes along flat, so files it loads beside itself are there
        parent = os.path.dirname(found)
        for name in names:
            if os.path.dirname(name) != parent:
                continue
            if name != found and name.lower().endswith('.dll'):
                continue
            # basename only: an archive cannot write outside the folder
            with archive.open(name) as source, \
                    open(os.path.join(folder, os.path.basename(name)), 'wb') as file:
                shutil.copyfileobj(source, file)
    return os.path.join(folder, os.path.basename(found))


def get_latest(family, name):
    # builds land in <family>\<stamp>\: a new path makes the engine load the new DLL without restarting audio
    folder = os.path.join(STORE, family)
    try:
        stamps = sorted(entry for entry in os.listdir(folder)
                        if os.path.isfile(os.path.join(folder, entry, name)))
    except OSError:
        return None
    return os.path.join(folder, stamps[-1], name) if stamps else None


def get_free_folder(folder):
    index = 2
    while os.path.isdir(f'{folder}-{index}'):
        index += 1
    return f'{folder}-{index}'


def is_stored(path):
    return bool(path) and os.path.normcase(os.path.abspath(path)).startswith(
        os.path.normcase(STORE) + os.sep)


def clean(path, used):
    # older versions beside path, unless a unit still uses one; a folder the engine holds stays for next time
    if not is_stored(path):
        return
    family = os.path.dirname(os.path.dirname(os.path.abspath(path)))
    keep = {os.path.normcase(os.path.dirname(os.path.abspath(item))) for item in used if item}
    for name in os.listdir(family):
        folder = os.path.join(family, name)
        if os.path.normcase(folder) not in keep:
            shutil.rmtree(folder, ignore_errors=True)

