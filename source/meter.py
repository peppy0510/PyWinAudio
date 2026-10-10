# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com

출력 장치로 나가는 소리를 WASAPI 루프백으로 받아 계기판에 넘긴다.

루프백은 Equalizer APO 가 다 처리한 뒤의 소리다(실측: 랙에 Preamp -12 dB 를 넣으면
시험음이 그만큼 내려가고, 8 kHz 저역 통과를 넣으면 18 kHz 가 사라진다). 그래서 계기판이
보여 주는 것이 곧 스피커로 나가는 것이다.

받기는 따로 도는 스레드가 맡고, 화면은 그 결과를 꺼내 그리기만 한다. 소리가 안 나는
동안 WASAPI 가 아무것도 주지 않는 장치가 있어, 그때는 받는 쪽이 0 을 채워 준다.
'''


import ctypes
import threading
import time
import warnings

import numpy


RATE = 48000
# 장치가 모아 둘 수 있는 양. 그 안에서 10 ms 마다 쌓인 만큼 한꺼번에 가져온다.
BUFFER = 4800
POLL = 0.010
HISTORY = 8192
RMS_WINDOW = 0.3
# 기본 출력 장치가 바뀌었는지 이만큼마다 본다.
DEVICE_CHECK = 2.0
RETRY_DELAY = 1.0
CLIP_LEVEL = 0.999
COINIT_MULTITHREADED = 0


class Capture:

    def __init__(self):
        self.lock = threading.Lock()
        self.history = numpy.zeros((HISTORY, 2), dtype='float32')
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
            self.squares[:] = 0
            self.peaks = [0.0, 0.0]

    def run(self):
        '''soundcard 는 가져온 스레드에서만 COM 을 연다. 껐다 켜면 새 스레드가 뜨므로
        여기서 직접 연다 — 안 그러면 0x800401f0(CO_E_NOTINITIALIZED) 로 죽는다.'''
        warnings.simplefilter('ignore')
        # 처음 가져올 때는 soundcard 가 이 스레드의 COM 을 스스로 열고, 이미 열려 있으면
        # (S_FALSE 를 실패로 읽어) 가져오기부터 죽는다. 그래서 가져온 다음에 연다.
        try:
            import soundcard
        except Exception as error:
            self.error = 'Could not load soundcard (%s)' % error
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
        # 정해진 수를 기다리게 하면 soundcard 가 1 ms 안쪽 간격으로 장치를 들여다본다
        # (받기만으로 CPU 8 %). 쉬었다가 쌓인 것만 가져오면 그 비용이 거의 사라진다.
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
            self.history = numpy.roll(self.history, -count, axis=0)
            self.history[-count:] = block
            end = self.square_index + count
            if end <= self.rms_window:
                self.squares[self.square_index:end] = squares
            else:
                split = self.rms_window - self.square_index
                self.squares[self.square_index:] = squares[:split]
                self.squares[:count - split] = squares[split:]
            self.square_index = end % self.rms_window
            # 화면이 꺼내 갈 때까지 가장 큰 값을 쌓아 둔다. 그 사이 지나간 순간 피크를 놓치지 않게.
            self.peaks = [max(self.peaks[0], float(peaks[0])), max(self.peaks[1], float(peaks[1]))]
            for channel in (0, 1):
                if peaks[channel] >= CLIP_LEVEL:
                    self.clips[channel] = True
            self.serial += 1

    def take(self, samples):
        '''(지난번 이후의 피크, RMS, 클립, 최근 표본 samples 개). 피크는 꺼내면 비운다.'''
        with self.lock:
            peaks = self.peaks
            self.peaks = [0.0, 0.0]
            rms = numpy.sqrt(self.squares.mean(axis=0))
            clips = list(self.clips)
            recent = self.history[-samples:].copy()
        return peaks, [float(rms[0]), float(rms[1])], clips, recent

    def reset_clips(self):
        with self.lock:
            self.clips = [False, False]


def to_db(value, floor=-120.0):
    return max(floor, 20 * numpy.log10(max(value, 1e-12)))
