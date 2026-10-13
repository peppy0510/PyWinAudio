# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com
'''


import cmath
import math


SAMPLE_RATE = 48000.0
LOW = 20.0
HIGH = 20000.0


def get_coefficients(band):
    kind = band['type']
    freq = min(max(band['freq'], 1.0), SAMPLE_RATE * 0.49)
    q = max(band.get('q', 0.707), 0.01)
    gain = band.get('gain', 0.0)
    amp = 10 ** (gain / 40)
    w0 = 2 * math.pi * freq / SAMPLE_RATE
    cos, alpha = math.cos(w0), math.sin(w0) / (2 * q)
    root = 2 * math.sqrt(amp) * alpha

    if kind == 'PK':
        return ((1 + alpha * amp, -2 * cos, 1 - alpha * amp),
                (1 + alpha / amp, -2 * cos, 1 - alpha / amp))
    if kind == 'LSC':
        return ((amp * ((amp + 1) - (amp - 1) * cos + root),
                 2 * amp * ((amp - 1) - (amp + 1) * cos),
                 amp * ((amp + 1) - (amp - 1) * cos - root)),
                ((amp + 1) + (amp - 1) * cos + root,
                 -2 * ((amp - 1) + (amp + 1) * cos),
                 (amp + 1) + (amp - 1) * cos - root))
    if kind == 'HSC':
        return ((amp * ((amp + 1) + (amp - 1) * cos + root),
                 -2 * amp * ((amp - 1) + (amp + 1) * cos),
                 amp * ((amp + 1) + (amp - 1) * cos - root)),
                ((amp + 1) - (amp - 1) * cos + root,
                 2 * ((amp - 1) - (amp + 1) * cos),
                 (amp + 1) - (amp - 1) * cos - root))
    if kind == 'HPQ':
        return (((1 + cos) / 2, -(1 + cos), (1 + cos) / 2),
                (1 + alpha, -2 * cos, 1 - alpha))
    if kind == 'LPQ':
        return (((1 - cos) / 2, 1 - cos, (1 - cos) / 2),
                (1 + alpha, -2 * cos, 1 - alpha))
    return ((1, 0, 0), (1, 0, 0))


def get_magnitude(coefficients, freq):
    (b0, b1, b2), (a0, a1, a2) = coefficients
    z = cmath.exp(-1j * 2 * math.pi * freq / SAMPLE_RATE)
    value = abs((b0 + b1 * z + b2 * z * z) / (a0 + a1 * z + a2 * z * z))
    return 20 * math.log10(max(value, 1e-9))


def get_frequencies(count):
    ratio = math.log(HIGH / LOW)
    return [LOW * math.exp(ratio * index / (count - 1)) for index in range(count)]


def get_band_curve(band, freqs):
    coefficients = get_coefficients(band)
    return [get_magnitude(coefficients, freq) for freq in freqs]


def get_parametric_curve(bands, freqs):
    total = [0.0] * len(freqs)
    for band in bands:
        if not band.get('on', True):
            continue
        for index, value in enumerate(get_band_curve(band, freqs)):
            total[index] += value
    return total


def get_graphic_curve(points, gains, freqs):
    # the engine joins points linearly on log frequency and holds the ends
    pairs = sorted(zip(points, gains))
    if not pairs:
        return [0.0] * len(freqs)
    curve = []
    for freq in freqs:
        if freq <= pairs[0][0]:
            curve.append(pairs[0][1])
            continue
        if freq >= pairs[-1][0]:
            curve.append(pairs[-1][1])
            continue
        for (low, low_gain), (high, high_gain) in zip(pairs, pairs[1:]):
            if low <= freq <= high:
                ratio = math.log(freq / low) / math.log(high / low) if high > low else 0
                curve.append(low_gain + (high_gain - low_gain) * ratio)
                break
    return curve


def get_unit_curve(unit, freqs):
    if not unit.get('on', True):
        return None
    if unit['kind'] == 'parametric':
        return get_parametric_curve(unit['bands'], freqs)
    if unit['kind'] == 'graphic':
        return get_graphic_curve(unit['freqs'], unit['gains'], freqs)
    return None


def get_peak_boost(units):
    freqs = get_frequencies(240)
    total = [0.0] * len(freqs)
    for unit in units:
        curve = get_unit_curve(unit, freqs)
        if curve:
            total = [a + b for a, b in zip(total, curve)]
    return max(total) if total else 0.0
