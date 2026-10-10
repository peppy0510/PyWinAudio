# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com

Equalizer APO 와 주고받는 것은 config 폴더의 글 파일뿐이다. 엔진은 그 폴더를
지켜보다가 파일이 바뀌면 스스로 다시 읽는다 — 앱 쪽에서 엔진을 부를 일은 없다.

config.txt 에는 `Include: pywinaudio.txt` 한 줄만 두고, 랙이 만든 내용은 모두
pywinaudio.txt 에 쓴다. 이어 붙이기 전의 config.txt 는 옆에 그대로 남겨 둔다.
'''


import os
import re
import shlex
import winreg


OWN_FILE = 'pywinaudio.txt'
BACKUP_FILE = 'config-before-pywinaudio.txt'
INCLUDE_LINE = 'Include: %s' % OWN_FILE

# 시험할 때 진짜 config 를 건드리지 않게 폴더를 바꿔 끼운다.
OVERRIDE = 'PYWINAUDIO_CONFIG'

HEADER = '# Written by PyWinAudio. Changes made here are overwritten by the app.'


def get_install_path():
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\EqualizerAPO') as key:
            return winreg.QueryValueEx(key, 'InstallPath')[0]
    except OSError:
        return None


def get_config_path():
    if os.environ.get(OVERRIDE):
        return os.environ[OVERRIDE]
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\EqualizerAPO') as key:
            path = winreg.QueryValueEx(key, 'ConfigPath')[0]
    except OSError:
        install = get_install_path()
        path = os.path.join(install, 'config') if install else None
    return path if path and os.path.isdir(path) else None


def get_device_selector():
    install = get_install_path()
    if not install:
        return None
    path = os.path.join(install, 'DeviceSelector.exe')
    return path if os.path.exists(path) else None


def read_text(path):
    '''엔진은 BOM 이 없으면 시스템 코드페이지로도 읽는다. 우리는 UTF-8 을 먼저 보고
    안 되면 mbcs 로 물러선다 — 손으로 쓴 옛 config 가 그런 경우가 있다.'''
    with open(path, 'rb') as file:
        raw = file.read()
    text = None
    for encoding in ('utf-8-sig', 'mbcs'):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        text = raw.decode('utf-8', 'replace')
    # 쓸 때 줄끝을 CRLF 로 바꾸므로 읽을 때 LF 로 모아 두어야 CR 이 겹치지 않는다.
    return text.replace('\r\n', '\n')


def write_text(path, text):
    '''다 쓴 뒤에 바꿔 끼운다. 엔진이 반쯤 쓴 파일을 읽어 가는 일을 막는다.'''
    temporary = path + '.tmp'
    with open(temporary, 'w', encoding='utf-8', newline='\r\n') as file:
        file.write(text)
    os.replace(temporary, path)


def is_include(line):
    match = re.match(r'\s*Include\s*:\s*(.+?)\s*$', line, re.IGNORECASE)
    return bool(match) and match.group(1).strip('"').lower() == OWN_FILE


def get_state(folder=None):
    '''('missing' | 'unlinked' | 'linked', config 폴더).'''
    folder = folder or get_config_path()
    if not folder:
        return 'missing', None
    path = os.path.join(folder, 'config.txt')
    if not os.path.exists(path):
        return 'unlinked', folder
    try:
        lines = read_text(path).splitlines()
    except OSError:
        return 'unlinked', folder
    for line in lines:
        if is_include(line):
            return 'linked', folder
    return 'unlinked', folder


def link(folder):
    '''config.txt 를 옆으로 옮겨 두고 Include 한 줄짜리로 바꾼다. 옮긴 내용 가운데 랙이
    읽을 수 있는 것은 단위로 바꿔 돌려준다 — 이어 붙인 순간 소리가 바뀌지 않게.'''
    path = os.path.join(folder, 'config.txt')
    text = read_text(path) if os.path.exists(path) else ''
    lines = [line for line in text.splitlines() if not is_include(line)]
    backup = os.path.join(folder, BACKUP_FILE)
    if lines and not os.path.exists(backup):
        write_text(backup, '\n'.join(lines) + '\n')
    units = parse('\n'.join(lines))
    write_text(path, '\n'.join([
        '# PyWinAudio writes the rack into %s.' % OWN_FILE,
        '# The lines that were here before are kept in %s.' % BACKUP_FILE,
        INCLUDE_LINE, '']))
    return units


def unlink(folder):
    '''옮겨 둔 config 를 되돌린다. 없으면 Include 줄만 걷어낸다.'''
    path = os.path.join(folder, 'config.txt')
    backup = os.path.join(folder, BACKUP_FILE)
    if os.path.exists(backup):
        write_text(path, read_text(backup))
        os.remove(backup)
    elif os.path.exists(path):
        lines = [line for line in read_text(path).splitlines() if not is_include(line)]
        write_text(path, '\n'.join(lines) + '\n')


def write_rack(folder, units, power=True):
    write_text(os.path.join(folder, OWN_FILE), render(units, power))


# ---------------------------------------------------------------- 단위 ↔ 글

FILTER_TYPES = ('PK', 'LSC', 'HSC', 'HPQ', 'LPQ')
# 옛 이름은 받아들이되 같은 모양의 Q 를 가진 이름으로 옮긴다.
FILTER_ALIASES = {'PEQ': 'PK', 'LS': 'LSC', 'HS': 'HSC', 'HP': 'HPQ', 'LP': 'LPQ'}

GRAPHIC_FREQUENCIES = (25, 40, 63, 100, 160, 250, 400, 630, 1000, 1600, 2500, 4000,
                       6300, 10000, 16000)


def get_number(value):
    text = ('%.4f' % value).rstrip('0').rstrip('.')
    return '0' if text in ('-0', '') else text


def quote(token):
    return '"%s"' % token if re.search(r'\s', token) or not token else token


def render_band(band):
    kind = band['type']
    parts = ['Filter: ON', kind, 'Fc', get_number(band['freq']), 'Hz']
    if kind in ('PK', 'LSC', 'HSC'):
        parts += ['Gain', get_number(band['gain']), 'dB']
    parts += ['Q', get_number(band['q'])]
    return ' '.join(parts)


def get_stereo_matrix(unit):
    '''가운데·옆 성분으로 폭을 정하고, 균형은 한쪽만 줄여 소리가 커지지 않게 한다.'''
    width = unit.get('width', 1.0)
    balance = unit.get('balance', 0.0)
    near, far = (1 + width) / 2, (1 - width) / 2
    left_gain = 1 - max(0.0, balance)
    right_gain = 1 + min(0.0, balance)
    left = (near * left_gain, far * left_gain)
    right = (far * right_gain, near * right_gain)
    if unit.get('swap'):
        left, right = right, left
    return left, right


def render_mix(target, pair):
    terms = []
    for gain, channel in zip(pair, ('L', 'R')):
        if abs(gain) < 1e-6:
            continue
        terms.append(channel if abs(gain - 1) < 1e-6 else '%s*%s' % (get_number(gain), channel))
    return '%s=%s' % (target, '+'.join(terms) if terms else '0')


def render_unit(unit):
    kind = unit['kind']
    if kind == 'preamp':
        return ['Preamp: %s dB' % get_number(unit['gain'])]
    if kind == 'parametric':
        return [render_band(band) for band in unit['bands'] if band.get('on', True)]
    if kind == 'graphic':
        pairs = zip(unit.get('freqs', GRAPHIC_FREQUENCIES), unit['gains'])
        return ['GraphicEQ: ' + '; '.join('%s %s' % (get_number(freq), get_number(gain))
                                          for freq, gain in pairs)]
    if kind == 'delay':
        lines = ['Delay: %s ms' % get_number(unit['ms'])]
        if unit.get('channel', 'all') != 'all':
            lines = ['Channel: %s' % unit['channel']] + lines + ['Channel: all']
        return lines
    if kind == 'stereo':
        left, right = get_stereo_matrix(unit)
        if left == (1, 0) and right == (0, 1):
            return []
        return ['Copy: %s %s' % (render_mix('L', left), render_mix('R', right))]
    if kind == 'vst':
        if not unit.get('path'):
            return []
        parts = ['VSTPlugin: Library', quote(unit['path'])]
        if unit.get('chunk'):
            parts += ['ChunkData', quote(unit['chunk'])]
        else:
            for name, value in unit.get('params', ()):
                parts += [quote(name), get_number(value)]
        return [' '.join(parts)]
    if kind == 'custom':
        return list(unit.get('lines', ()))
    return []


LABELS = {'preamp': 'Preamp', 'parametric': 'Parametric EQ', 'graphic': 'Graphic EQ',
          'delay': 'Delay', 'stereo': 'Stereo', 'vst': 'VST plugin', 'custom': 'Custom lines'}


def render(units, power=True):
    lines = [HEADER]
    if not power:
        lines.append('# The rack is switched off.')
        return '\n'.join(lines) + '\n'
    for unit in units:
        if not unit.get('on', True):
            continue
        body = render_unit(unit)
        if body:
            lines.append('')
            label = unit.get('title') or (unit.get('name') if unit['kind'] == 'vst' else None)
            lines.append('# %s' % (label or LABELS.get(unit['kind'], unit['kind'])))
            lines.extend(body)
    return '\n'.join(lines) + '\n'


def tokenize(text):
    try:
        return shlex.split(text, posix=True)
    except ValueError:
        return text.split()


def parse_band(text):
    tokens = tokenize(text)
    if not tokens or tokens[0].upper() not in ('ON', 'OFF'):
        return None
    on = tokens[0].upper() == 'ON'
    if len(tokens) < 2:
        return None
    kind = tokens[1].upper()
    kind = FILTER_ALIASES.get(kind, kind)
    if kind not in FILTER_TYPES:
        return None
    band = {'type': kind, 'freq': 1000.0, 'gain': 0.0, 'q': 0.707 if kind != 'PK' else 1.0,
            'on': on}
    keys = {'FC': 'freq', 'GAIN': 'gain', 'Q': 'q'}
    for index, token in enumerate(tokens):
        key = keys.get(token.upper())
        if key and index + 1 < len(tokens):
            try:
                band[key] = float(tokens[index + 1])
            except ValueError:
                return None
    return band


def parse_vst(text):
    tokens = tokenize(text)
    unit = {'kind': 'vst', 'on': True, 'path': '', 'params': [], 'chunk': None}
    index = 0
    while index < len(tokens):
        token = tokens[index]
        value = tokens[index + 1] if index + 1 < len(tokens) else ''
        if token.lower() == 'library':
            unit['path'] = value
        elif token.lower() == 'chunkdata':
            unit['chunk'] = value
        else:
            try:
                unit['params'].append([token, float(value)])
            except ValueError:
                return None
        index += 2
    if not unit['path']:
        return None
    unit['name'] = os.path.splitext(os.path.basename(unit['path']))[0]
    return unit


def parse(text):
    '''읽을 수 있는 줄은 단위로, 나머지는 Custom 단위에 차례 그대로 담는다.
    주석과 빈 줄은 버린다.'''
    units = []

    def add_custom(line):
        if units and units[-1]['kind'] == 'custom':
            units[-1]['lines'].append(line)
        else:
            units.append({'kind': 'custom', 'on': True, 'lines': [line]})

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        match = re.match(r'([A-Za-z]+)(?:\s+\d+)?\s*:\s*(.*)$', stripped)
        if not match:
            add_custom(stripped)
            continue
        command, body = match.group(1).lower(), match.group(2)

        if command == 'preamp':
            found = re.match(r'(-?[\d.]+)\s*dB', body, re.IGNORECASE)
            if found:
                units.append({'kind': 'preamp', 'on': True, 'gain': float(found.group(1))})
                continue
        elif command == 'filter':
            band = parse_band(body)
            if band:
                if units and units[-1]['kind'] == 'parametric':
                    units[-1]['bands'].append(band)
                else:
                    units.append({'kind': 'parametric', 'on': True, 'bands': [band]})
                continue
        elif command == 'graphiceq':
            pairs = []
            for item in body.split(';'):
                values = item.split()
                if len(values) == 2:
                    try:
                        pairs.append((float(values[0]), float(values[1])))
                    except ValueError:
                        pairs = None
                        break
            if pairs:
                units.append({'kind': 'graphic', 'on': True,
                              'freqs': [freq for freq, gain in pairs],
                              'gains': [gain for freq, gain in pairs]})
                continue
        elif command == 'delay':
            found = re.match(r'(-?[\d.]+)\s*ms\s*$', body, re.IGNORECASE)
            if found:
                units.append({'kind': 'delay', 'on': True, 'ms': float(found.group(1)),
                              'channel': 'all'})
                continue
        elif command == 'vstplugin':
            unit = parse_vst(body)
            if unit:
                units.append(unit)
                continue
        add_custom(stripped)
    return units
