"""Bounded PCM-to-display analysis. No imports, devices or retained audio at idle."""
import cmath
import math
import struct


def analyze(pcm):
    """Same fixed-calibration 1024-sample/32-band DSP as the native preview."""
    if len(pcm) != 2048:
        return 0.0, [0.0] * 32
    samples = [x / 32768.0 for x in struct.unpack("<1024h", pcm)]
    mean = sum(samples) / 1024
    samples = [x - mean for x in samples]
    bins = [complex(x * (.5 - .5 * math.cos(2 * math.pi * i / 1023))) for i, x in enumerate(samples)]
    j = 0
    for i in range(1, 1024):
        bit = 512
        while j & bit:
            j ^= bit
            bit >>= 1
        j ^= bit
        if i < j:
            bins[i], bins[j] = bins[j], bins[i]
    length = 2
    while length <= 1024:
        step = cmath.exp(-2j * math.pi / length)
        for start in range(0, 1024, length):
            phase = 1
            for offset in range(length // 2):
                even, odd = bins[start + offset], bins[start + offset + length // 2] * phase
                bins[start + offset], bins[start + offset + length // 2] = even + odd, even - odd
                phase *= step
        length *= 2
    def level(magnitude, floor, ceiling):
        x = max(0., min(1., (20 * math.log10(max(magnitude, 1e-12)) - floor) / (ceiling - floor)))
        return x * x * (3 - 2 * x)
    amplitude = level(math.sqrt(sum(x*x for x in samples) / 1024), -55, -14)
    bands = []
    for band in range(32):
        first = max(1, min(511, math.ceil(80 * 100 ** (band / 32) * 1024 / 16000)))
        end = max(first + 1, min(512, math.ceil(80 * 100 ** ((band + 1) / 32) * 1024 / 16000)))
        magnitude = 2 * math.sqrt(sum(abs(bins[k]) ** 2 for k in range(first, end))) / 1024
        bands.append(level(magnitude, -65, -20) * amplitude)
    return amplitude, bands
