# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com

PyWinAudio Leveler 가 audiodg 안에서 적어 두는 계기 값을 읽는다. 플러그인은 인스턴스마다
공유 메모리 "Global\\PyWinAudioLeveler" 의 칸 하나에 블록마다 지금 거는 보정 값을 적는다
(plugin/leveler.c 의 MeterBlock 과 같은 배치). 여기서는 가장 최근에 소리를 처리한 칸을 고른다.
'''


import ctypes

from ctypes import wintypes


MAGIC = 0x4D4C5750  # 'PWLM'
SLOTS = 8
NAMES = ('Global\\PyWinAudioLeveler', 'Local\\PyWinAudioLeveler')
FILE_MAP_READ = 0x0004
# 이보다 오래 소식이 없으면(소리가 멈췄거나 플러그인이 내려갔으면) 값을 보이지 않는다.
STALE_MS = 1500


class Slot(ctypes.Structure):
    _fields_ = [('owner', ctypes.c_int64), ('tick', ctypes.c_int64),
                ('agc_db', ctypes.c_float), ('balance_db', ctypes.c_float),
                ('side_db', ctypes.c_float), ('fill_db', ctypes.c_float),
                ('limiter_db', ctypes.c_float), ('loudness', ctypes.c_float),
                ('sounding', ctypes.c_int32), ('reserved', ctypes.c_int32)]


class Block(ctypes.Structure):
    _fields_ = [('magic', ctypes.c_uint32), ('version', ctypes.c_uint32),
                ('slots', Slot * SLOTS)]


kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
kernel32.OpenFileMappingW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.OpenFileMappingW.restype = wintypes.HANDLE
kernel32.MapViewOfFile.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
                                   wintypes.DWORD, ctypes.c_size_t]
kernel32.MapViewOfFile.restype = ctypes.c_void_p
kernel32.GetTickCount64.restype = ctypes.c_uint64


class Reader:
    '''공유 메모리를 한 번 열어 두고 읽는다. 아직 없으면(플러그인이 소리를 처리한 적이 없으면)
    부를 때마다 다시 열어 본다.'''

    def __init__(self):
        self.block = None

    def open(self):
        for name in NAMES:
            handle = kernel32.OpenFileMappingW(FILE_MAP_READ, False, name)
            if not handle:
                continue
            address = kernel32.MapViewOfFile(handle, FILE_MAP_READ, 0, 0, ctypes.sizeof(Block))
            if address:
                self.block = Block.from_address(address)
                self.handle = handle
                return True
        return False

    def read(self):
        '''가장 최근에 소리를 처리한 칸의 값(dict). 없으면 None.'''
        if self.block is None and not self.open():
            return None
        if self.block.magic != MAGIC:
            return None
        now = kernel32.GetTickCount64()
        best = None
        for slot in self.block.slots:
            if not slot.owner or not slot.tick or now - slot.tick > STALE_MS:
                continue
            key = (slot.sounding, slot.tick)
            if best is None or key > best[0]:
                best = (key, slot)
        if best is None:
            return None
        slot = best[1]
        return {'agc': slot.agc_db, 'balance': slot.balance_db, 'side': slot.side_db,
                'fill': slot.fill_db, 'limiter': slot.limiter_db, 'loudness': slot.loudness,
                'sounding': bool(slot.sounding)}


READER = Reader()
