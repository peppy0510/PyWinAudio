# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com
'''


import base64
import ctypes
import os

from ctypes import wintypes


MAGIC = 0x56737450  # 'VstP'

EFF_OPEN = 0
EFF_CLOSE = 1
EFF_GET_PARAM_LABEL = 6
EFF_GET_PARAM_DISPLAY = 7
EFF_GET_PARAM_NAME = 8
EFF_SET_SAMPLE_RATE = 10
EFF_SET_BLOCK_SIZE = 11
EFF_MAINS_CHANGED = 12
EFF_EDIT_GET_RECT = 13
EFF_EDIT_OPEN = 14
EFF_EDIT_CLOSE = 15
EFF_EDIT_IDLE = 19
EFF_GET_CHUNK = 23
EFF_SET_CHUNK = 24
EFF_GET_EFFECT_NAME = 45
EFF_GET_VENDOR_STRING = 47
EFF_GET_PRODUCT_STRING = 48
EFF_GET_PARAMETER_PROPERTIES = 56

PARAM_IS_SWITCH = 1 << 0
PARAM_SUPPORTS_DISPLAY_CATEGORY = 1 << 5

FLAG_HAS_EDITOR = 1 << 0
FLAG_PROGRAM_CHUNKS = 1 << 5

MASTER_AUTOMATE = 0
MASTER_VERSION = 1
MASTER_CURRENT_ID = 2
MASTER_IDLE = 3
MASTER_SIZE_WINDOW = 15
MASTER_GET_SAMPLE_RATE = 16
MASTER_GET_BLOCK_SIZE = 17
MASTER_GET_VENDOR_STRING = 32
MASTER_GET_PRODUCT_STRING = 33
MASTER_GET_VENDOR_VERSION = 34
MASTER_CAN_DO = 37
MASTER_UPDATE_DISPLAY = 42
MASTER_BEGIN_EDIT = 43
MASTER_END_EDIT = 44

SAMPLE_RATE = 48000.0
BLOCK_SIZE = 512

# names are 8-64 bytes by spec, but plugins often write more
TEXT_SIZE = 256


class AEffect(ctypes.Structure):
    pass


Dispatcher = ctypes.CFUNCTYPE(ctypes.c_ssize_t, ctypes.POINTER(AEffect), ctypes.c_int32,
                              ctypes.c_int32, ctypes.c_ssize_t, ctypes.c_void_p,
                              ctypes.c_float)
SetParameter = ctypes.CFUNCTYPE(None, ctypes.POINTER(AEffect), ctypes.c_int32,
                                ctypes.c_float)
GetParameter = ctypes.CFUNCTYPE(ctypes.c_float, ctypes.POINTER(AEffect), ctypes.c_int32)
AudioMaster = ctypes.CFUNCTYPE(ctypes.c_ssize_t, ctypes.POINTER(AEffect), ctypes.c_int32,
                               ctypes.c_int32, ctypes.c_ssize_t, ctypes.c_void_p,
                               ctypes.c_float)
EntryPoint = ctypes.CFUNCTYPE(ctypes.POINTER(AEffect), AudioMaster)

AEffect._fields_ = [
    ('magic', ctypes.c_int32),
    ('dispatcher', Dispatcher),
    ('process', ctypes.c_void_p),
    ('setParameter', SetParameter),
    ('getParameter', GetParameter),
    ('numPrograms', ctypes.c_int32),
    ('numParams', ctypes.c_int32),
    ('numInputs', ctypes.c_int32),
    ('numOutputs', ctypes.c_int32),
    ('flags', ctypes.c_int32),
    ('resvd1', ctypes.c_ssize_t),
    ('resvd2', ctypes.c_ssize_t),
    ('initialDelay', ctypes.c_int32),
    ('realQualities', ctypes.c_int32),
    ('offQualities', ctypes.c_int32),
    ('ioRatio', ctypes.c_float),
    ('object', ctypes.c_void_p),
    ('user', ctypes.c_void_p),
    ('uniqueID', ctypes.c_int32),
    ('version', ctypes.c_int32),
    ('processReplacing', ctypes.c_void_p),
    ('processDoubleReplacing', ctypes.c_void_p),
    ('future', ctypes.c_char * 56),
]


class ParameterProperties(ctypes.Structure):
    _fields_ = [('stepFloat', ctypes.c_float), ('smallStepFloat', ctypes.c_float),
                ('largeStepFloat', ctypes.c_float), ('label', ctypes.c_char * 64),
                ('flags', ctypes.c_int32), ('minInteger', ctypes.c_int32),
                ('maxInteger', ctypes.c_int32), ('stepInteger', ctypes.c_int32),
                ('largeStepInteger', ctypes.c_int32), ('shortLabel', ctypes.c_char * 8),
                ('displayIndex', ctypes.c_int16), ('category', ctypes.c_int16),
                ('numParametersInCategory', ctypes.c_int16), ('reserved', ctypes.c_int16),
                ('categoryLabel', ctypes.c_char * 24), ('future', ctypes.c_char * 16)]


class ERect(ctypes.Structure):
    _fields_ = [('top', ctypes.c_int16), ('left', ctypes.c_int16),
                ('bottom', ctypes.c_int16), ('right', ctypes.c_int16)]


class VstError(Exception):
    pass


kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
kernel32.LoadLibraryW.argtypes = [wintypes.LPCWSTR]
kernel32.LoadLibraryW.restype = wintypes.HMODULE
kernel32.GetProcAddress.argtypes = [wintypes.HMODULE, ctypes.c_char_p]
kernel32.GetProcAddress.restype = ctypes.c_void_p
kernel32.FreeLibrary.argtypes = [wintypes.HMODULE]


def get_bitness(path):
    # a 32-bit plugin cannot load into this process
    try:
        with open(path, 'rb') as file:
            head = file.read(4096)
        offset = int.from_bytes(head[0x3c:0x40], 'little')
        machine = int.from_bytes(head[offset + 4:offset + 6], 'little')
    except Exception:
        return None
    return {0x8664: 64, 0xaa64: 64, 0x14c: 32}.get(machine)


class Plugin:
    # always close: unloading the DLL with its editor open crashes on the next message

    def __init__(self, path, on_change=None):
        self.path = path
        self.on_change = on_change
        self.module = None
        self.effect = None
        self.editor = False

        if get_bitness(path) == 32:
            raise VstError('32-bit plugin')
        # let the plugin find the DLLs beside it
        directory = os.path.dirname(path)
        cookie = None
        try:
            cookie = os.add_dll_directory(directory)
        except Exception:
            pass
        try:
            self.module = kernel32.LoadLibraryW(path)
        finally:
            if cookie is not None:
                cookie.close()
        if not self.module:
            raise VstError(f'Could not load the library (error {ctypes.get_last_error()})')

        address = None
        for name in (b'VSTPluginMain', b'main'):
            address = kernel32.GetProcAddress(self.module, name)
            if address:
                break
        if not address:
            self.unload()
            raise VstError('Not a VST2 plugin')

        # keep the callback referenced, or GC frees it and the plugin calls a dead address
        self.master = AudioMaster(self.on_master)
        pointer = EntryPoint(address)(self.master)
        if not pointer or pointer.contents.magic != MAGIC:
            self.unload()
            raise VstError('Not a VST2 plugin')
        self.pointer = pointer
        self.effect = pointer.contents

        self.call(EFF_OPEN)
        self.call(EFF_SET_SAMPLE_RATE, option=SAMPLE_RATE)
        self.call(EFF_SET_BLOCK_SIZE, value=BLOCK_SIZE)
        self.call(EFF_MAINS_CHANGED, value=1)

    def on_master(self, effect, opcode, index, value, pointer, option):
        if opcode == MASTER_VERSION:
            return 2400
        if opcode == MASTER_AUTOMATE:
            if self.on_change:
                self.on_change(index, option)
            return 0
        if opcode == MASTER_GET_SAMPLE_RATE:
            return int(SAMPLE_RATE)
        if opcode == MASTER_GET_BLOCK_SIZE:
            return BLOCK_SIZE
        if opcode in (MASTER_GET_VENDOR_STRING, MASTER_GET_PRODUCT_STRING) and pointer:
            ctypes.memmove(pointer, b'PyWinAudio\0', 11)
            return 1
        if opcode == MASTER_GET_VENDOR_VERSION:
            return 1
        if opcode == MASTER_CAN_DO and pointer:
            text = ctypes.string_at(pointer)
            return 1 if text in (b'sizeWindow',) else 0
        if opcode == MASTER_SIZE_WINDOW:
            self.requested_size = (index, value)
            return 1
        if opcode in (MASTER_UPDATE_DISPLAY, MASTER_BEGIN_EDIT, MASTER_END_EDIT,
                      MASTER_IDLE, MASTER_CURRENT_ID):
            return 0
        return 0

    requested_size = None

    def call(self, opcode, index=0, value=0, pointer=None, option=0.0):
        return self.effect.dispatcher(self.pointer, opcode, index, value, pointer, option)

    def get_text(self, opcode, index=0):
        buffer = ctypes.create_string_buffer(TEXT_SIZE)
        self.call(opcode, index, 0, ctypes.cast(buffer, ctypes.c_void_p))
        return buffer.value.decode('mbcs', 'replace').strip()

    @property
    def name(self):
        return (self.get_text(EFF_GET_EFFECT_NAME) or self.get_text(EFF_GET_PRODUCT_STRING)
                or os.path.splitext(os.path.basename(self.path))[0])

    @property
    def vendor(self):
        return self.get_text(EFF_GET_VENDOR_STRING)

    @property
    def count(self):
        return self.effect.numParams

    @property
    def uses_chunks(self):
        return bool(self.effect.flags & FLAG_PROGRAM_CHUNKS)

    @property
    def has_editor(self):
        return bool(self.effect.flags & FLAG_HAS_EDITOR)

    def get_name(self, index):
        return self.get_text(EFF_GET_PARAM_NAME, index)

    def get_display(self, index):
        return self.get_text(EFF_GET_PARAM_DISPLAY, index)

    def get_properties(self, index):
        props = ParameterProperties()
        try:
            if not self.call(EFF_GET_PARAMETER_PROPERTIES, index, 0,
                             ctypes.cast(ctypes.byref(props), ctypes.c_void_p)):
                return 0, None
        except Exception:
            return 0, None
        category = props.category if props.flags & PARAM_SUPPORTS_DISPLAY_CATEGORY else 0
        return int(category), bool(props.flags & PARAM_IS_SWITCH)

    def get_label(self, index):
        return self.get_text(EFF_GET_PARAM_LABEL, index)

    def get_value(self, index):
        return self.effect.getParameter(self.pointer, index)

    def set_value(self, index, value):
        self.effect.setParameter(self.pointer, index, float(value))

    def get_chunk(self):
        data = ctypes.c_void_p()
        size = self.call(EFF_GET_CHUNK, 0, 0, ctypes.cast(ctypes.byref(data), ctypes.c_void_p))
        if size <= 0 or not data.value:
            return None
        return base64.b64encode(ctypes.string_at(data.value, size)).decode('ascii')

    def set_chunk(self, text):
        try:
            raw = base64.b64decode(text)
        except Exception:
            return False
        # the buffer must live until the plugin has read it
        self.chunk_buffer = ctypes.create_string_buffer(raw, len(raw))
        self.call(EFF_SET_CHUNK, 0, len(raw), ctypes.cast(self.chunk_buffer, ctypes.c_void_p))
        return True

    def get_editor_size(self):
        rect = ctypes.POINTER(ERect)()
        self.call(EFF_EDIT_GET_RECT, 0, 0, ctypes.cast(ctypes.byref(rect), ctypes.c_void_p))
        if not rect:
            return None
        value = rect.contents
        width, height = value.right - value.left, value.bottom - value.top
        return (width, height) if width > 0 and height > 0 else None

    def open_editor(self, handle):
        # some plugins answer the size only after opening, so ask twice
        if not self.has_editor or self.editor:
            return None
        size = self.get_editor_size()
        self.call(EFF_EDIT_OPEN, 0, 0, ctypes.c_void_p(handle))
        self.editor = True
        return self.get_editor_size() or size

    def idle(self):
        if self.editor:
            self.call(EFF_EDIT_IDLE)

    def close_editor(self):
        if self.editor:
            self.editor = False
            self.call(EFF_EDIT_CLOSE)

    def close(self):
        if self.effect is None:
            return
        self.close_editor()
        self.call(EFF_MAINS_CHANGED, value=0)
        self.call(EFF_CLOSE)
        self.effect = None
        self.unload()

    def unload(self):
        if self.module:
            kernel32.FreeLibrary(self.module)
            self.module = None
