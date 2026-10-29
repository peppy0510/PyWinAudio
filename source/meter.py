# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com
'''


import ctypes
import math
import threading
import time
import warnings

import numpy


RATE = 48000
BUFFER = 4800
POLL = 0.010
HISTORY = 8192
RMS_WINDOW = 0.3
DEVICE_CHECK = 2.0
RETRY_DELAY = 1.0
CLIP_LEVEL = 0.999

# ITU-R BS.1770 K-weighting at 48 kHz, applied as FFT bin weights per 100 ms block
K_STAGES = (
    ((1.53512485958697, -2.69169618940638, 1.19839281085285),
     (1.0, -1.69065929318241, 0.73248077421585)),
    ((1.0, -2.0, 1.0), (1.0, -1.99004745483398, 0.99007225036621)),
)
LOUDNESS_BLOCK = RATE // 10
MOMENTARY_BLOCKS = 4
SHORT_BLOCKS = 30
ABSOLUTE_GATE = -70.0
RELATIVE_GATE = -10.0
LOUDNESS_FLOOR = -70.0
# one hour of 100 ms blocks
INTEGRATED_LIMIT = 36000


def get_k_weights(size):
    freqs = numpy.fft.rfftfreq(size, 1.0 / RATE)
    z = numpy.exp(-2j * numpy.pi * freqs / RATE)
    response = numpy.ones(len(freqs), dtype='complex128')
    for (b0, b1, b2), (a0, a1, a2) in K_STAGES:
        response *= (b0 + b1 * z + b2 * z * z) / (a0 + a1 * z + a2 * z * z)
    return numpy.abs(response) ** 2


K_WEIGHTS = get_k_weights(LOUDNESS_BLOCK)


def to_lufs(power):
    return max(LOUDNESS_FLOOR, -0.691 + 10 * math.log10(max(power, 1e-12)))
COINIT_MULTITHREADED = 0


class Capture:

    def __init__(self):
        self.lock = threading.Lock()
        self.history = numpy.zeros((HISTORY, 2), dtype='float32')
        self.history_index = 0
        self.peaks = [0.0, 0.0]
        self.clips = [False, False]
        self.rms_window = int(RATE * RMS_WINDOW)
        self.squares = numpy.zeros((self.rms_window, 2), dtype='float64')
        self.square_index = 0
        self.device = ''
        self.error = ''
        self.running = False
        self.thread = None
        self.serial = 0
        self.pending = numpy.zeros((0, 2), dtype='float32')
        self.blocks = []
        self.gated = []

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self.run, name='meter-capture', daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread is not None:
            self.thread.join(timeout=1.0)
            self.thread = None
        with self.lock:
            self.history[:] = 0
            self.history_index = 0
            self.squares[:] = 0
            self.peaks = [0.0, 0.0]
            self.blocks = []
            self.pending = numpy.zeros((0, 2), dtype='float32')

    def run(self):
        warnings.simplefilter('ignore')
        # import first: soundcard fails when COM is already open, and a new thread needs its own
        try:
            import soundcard
        except Exception as error:
            self.error = f'Could not load soundcard ({error})'
            return
        result = ctypes.windll.ole32.CoInitializeEx(None, COINIT_MULTITHREADED)
        try:
            self.loop(soundcard)
        finally:
            if result >= 0:
                ctypes.windll.ole32.CoUninitialize()

    def loop(self, soundcard):
        while self.running:
            try:
                speaker = soundcard.default_speaker()
                microphone = soundcard.get_microphone(speaker.id, include_loopback=True)
                self.device = speaker.name
                self.error = ''
                self.listen(soundcard, microphone, speaker.id)
            except Exception as error:
                self.error = str(error) or type(error).__name__
                self.device = ''
                time.sleep(RETRY_DELAY)

    def listen(self, soundcard, microphone, device_id):
        checked = time.perf_counter()
        # record(numframes=N) polls the device under 1 ms (8 % CPU); sleep and take what piled up
        with microphone.recorder(samplerate=RATE, channels=2, blocksize=BUFFER) as recorder:
            while self.running:
                time.sleep(POLL)
                block = recorder.record(numframes=None)
                if len(block):
                    self.feed(block)
                now = time.perf_counter()
                if now - checked > DEVICE_CHECK:
                    checked = now
                    if soundcard.default_speaker().id != device_id:
                        return

    def feed(self, block):
        if block.ndim == 1 or block.shape[1] == 1:
            block = numpy.repeat(block.reshape(-1, 1), 2, axis=1)
        block = block[:, :2].astype('float32')
        count = len(block)
        peaks = numpy.abs(block).max(axis=0)
        squares = block.astype('float64') ** 2
        with self.lock:
            if count >= HISTORY:
                self.history[:] = block[-HISTORY:]
                self.history_index = 0
            else:
                end = self.history_index + count
                if end <= HISTORY:
                    self.history[self.history_index:end] = block
                else:
                    split = HISTORY - self.history_index
                    self.history[self.history_index:] = block[:split]
                    self.history[:count - split] = block[split:]
                self.history_index = end % HISTORY
            end = self.square_index + count
            if end <= self.rms_window:
                self.squares[self.square_index:end] = squares
            else:
                split = self.rms_window - self.square_index
                self.squares[self.square_index:] = squares[:split]
                self.squares[:count - split] = squares[split:]
            self.square_index = end % self.rms_window
            # keep the highest peak until the screen takes it
            self.peaks = [max(self.peaks[0], float(peaks[0])), max(self.peaks[1], float(peaks[1]))]
            for channel in (0, 1):
                if peaks[channel] >= CLIP_LEVEL:
                    self.clips[channel] = True
            self.serial += 1
        self.feed_loudness(block)

    def feed_loudness(self, block):
        # BS.1770 gating blocks: 400 ms windows, 75 % overlap
        self.pending = numpy.concatenate((self.pending, block))
        while len(self.pending) >= LOUDNESS_BLOCK:
            part, self.pending = self.pending[:LOUDNESS_BLOCK], self.pending[LOUDNESS_BLOCK:]
            spectrum = numpy.abs(numpy.fft.rfft(part.astype('float64'), axis=0)) ** 2
            # one-sided spectrum: count all but DC and Nyquist twice
            spectrum[1:-1] *= 2
            power = float((spectrum * K_WEIGHTS[:, None]).sum()) / LOUDNESS_BLOCK ** 2
            with self.lock:
                self.blocks.append(power)
                del self.blocks[:-SHORT_BLOCKS]
                if len(self.blocks) >= MOMENTARY_BLOCKS:
                    momentary = sum(self.blocks[-MOMENTARY_BLOCKS:]) / MOMENTARY_BLOCKS
                    if to_lufs(momentary) > ABSOLUTE_GATE:
                        self.gated.append(momentary)
                        del self.gated[:-INTEGRATED_LIMIT]

    def take_loudness(self):
        with self.lock:
            blocks = list(self.blocks)
            gated = numpy.array(self.gated) if self.gated else None
        momentary = (sum(blocks[-MOMENTARY_BLOCKS:]) / MOMENTARY_BLOCKS
                     if len(blocks) >= MOMENTARY_BLOCKS else 0.0)
        short = sum(blocks) / len(blocks) if len(blocks) >= SHORT_BLOCKS else 0.0
        integrated = LOUDNESS_FLOOR
        if gated is not None and len(gated):
            threshold = to_lufs(float(gated.mean())) + RELATIVE_GATE
            kept = gated[-0.691 + 10 * numpy.log10(numpy.maximum(gated, 1e-12)) > threshold]
            if len(kept):
                integrated = to_lufs(float(kept.mean()))
        return to_lufs(momentary), to_lufs(short), integrated

    def reset_integrated(self):
        with self.lock:
            self.gated = []

    def take(self, samples):
        with self.lock:
            peaks = self.peaks
            self.peaks = [0.0, 0.0]
            rms = numpy.sqrt(self.squares.mean(axis=0))
            clips = list(self.clips)
            recent = numpy.roll(self.history, -self.history_index, axis=0)[-samples:]
        return peaks, [float(rms[0]), float(rms[1])], clips, recent

    def reset_clips(self):
        with self.lock:
            self.clips = [False, False]


def to_db(value, floor=-120.0):
    return max(floor, 20 * numpy.log10(max(value, 1e-12)))
