# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com
'''


import ctypes

from ctypes import wintypes


MAGIC = 0x4D415750  # 'PWAM'
SLOTS = 8
# bump the name with the plugin when the layout changes
NAMES = ('Global\\PyWinAudioAutoMaster.v4', 'Local\\PyWinAudioAutoMaster.v4')
FILE_MAP_WRITE = 0x0002
FILE_MAP_READ = 0x0004
# older slots mean silence or an unloaded plugin
STALE_MS = 1500


class Slot(ctypes.Structure):
    _fields_ = [('owner', ctypes.c_int64), ('tick', ctypes.c_int64),
                ('agc_db', ctypes.c_float), ('balance_db', ctypes.c_float),
                ('side_db', ctypes.c_float), ('fill_db', ctypes.c_float),
                ('limiter_db', ctypes.c_float), ('loudness', ctypes.c_float),
                ('sounding', ctypes.c_int32), ('phase_flip', ctypes.c_int32),
                ('fill_band_db', ctypes.c_float * 3), ('phase_delay_ms', ctypes.c_float),
                ('band_width_db', ctypes.c_float * 3), ('band_target_db', ctypes.c_float * 3)]


class Block(ctypes.Structure):
    _fields_ = [('magic', ctypes.c_uint32), ('version', ctypes.c_uint32),
                ('bypass', ctypes.c_int32), ('reserved', ctypes.c_uint32),
                ('slots', Slot * SLOTS)]


kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
kernel32.OpenFileMappingW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.OpenFileMappingW.restype = wintypes.HANDLE
kernel32.MapViewOfFile.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
                                   wintypes.DWORD, ctypes.c_size_t]
kernel32.MapViewOfFile.restype = ctypes.c_void_p
kernel32.GetTickCount64.restype = ctypes.c_uint64


class Reader:

    def __init__(self):
        self.block = None

    def open(self):
        for name in NAMES:
            # opened writable for the A/B flag
            handle = kernel32.OpenFileMappingW(FILE_MAP_READ | FILE_MAP_WRITE, False, name)
            if not handle:
                continue
            address = kernel32.MapViewOfFile(handle, FILE_MAP_READ | FILE_MAP_WRITE, 0, 0,
                                             ctypes.sizeof(Block))
            if address:
                self.block = Block.from_address(address)
                self.handle = handle
                return True
        return False

    def read(self):
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
                'fill': slot.fill_db, 'fill_low': slot.fill_band_db[0], 'fill_mid': slot.fill_band_db[1],
                'fill_high': slot.fill_band_db[2], 'limiter': slot.limiter_db, 'loudness': slot.loudness,
                'phase': slot.phase_delay_ms, 'phase_flip': bool(slot.phase_flip),
                'bands': [{'in': slot.band_width_db[k], 'fill': slot.fill_band_db[k],
                           'target': slot.band_target_db[k]} for k in range(3)],
                'sounding': bool(slot.sounding)}


    def get_bypass(self):
        return bool(self.block is not None and self.block.bypass)

    def set_bypass(self, on):
        if self.block is None and not self.open():
            return False
        self.block.bypass = 1 if on else 0
        return True


READER = Reader()
