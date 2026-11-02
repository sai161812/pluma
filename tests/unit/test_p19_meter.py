"""Measured fixture PCM and metadata only; never opens a device."""
import math
import struct
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from pluma.core.ipc_contracts import VoiceMeterV1
from pluma.voice.capture import AudioCapture
from pluma.voice.meter import analyze
from pluma.voice.vad import EnergyVAD


def tone(frequency=440, samples=1024, amplitude=8000):
    return struct.pack('<' + 'h'*samples, *(int(amplitude*math.sin(2*math.pi*frequency*i/16000)) for i in range(samples)))


def test_meter_is_actual_frequency_and_level_not_activity_animation():
    assert analyze(bytes(2048)) == (0., [0.] * 32)
    assert analyze(struct.pack('<1024h', *([8000]*1024))) == (0., [0.] * 32)
    low, bands = analyze(tone(440, amplitude=1000))
    high, strong = analyze(tone(440))
    assert 0 < low < high <= 1 and max(strong) > max(bands)
    peak = max(range(32), key=lambda i: strong[i])
    assert 80 * 100 ** (peak/32) <= 440 <= 80 * 100 ** ((peak+1)/32)
    assert analyze(b'')[0] == 0


def test_capture_meter_and_silence_progress_are_read_only_measured_frames():
    capture = AudioCapture(vad=EnergyVAD())
    capture._is_recording = True  # Inert capture, no stream created.
    capture.feed(tone(samples=16000))
    active, boundary, speech = capture.live_observation()
    assert active and not boundary and speech['speech_active'] and speech['amplitude'] > 0
    assert speech['sample_sequence'] == 16000
    capture.feed(bytes(3200))  # 100 ms, below configured trailing silence.
    _, boundary, silence = capture.live_observation()
    assert not boundary and not silence['speech_active'] and 0 < silence['silence_progress'] < 1
    assert capture.live_observation()[2] == silence  # Waiting does not invent progress.
    assert silence['sample_sequence'] > speech['sample_sequence']
    capture.feed(bytes(32000))
    active, boundary, end = capture.live_observation()
    assert not active and boundary and end['silence_progress'] == 1 and end['amplitude'] == 0
    capture.cancel()
    assert capture.capture_closed


@pytest.mark.parametrize('changes', [dict(bands=[0.]*31), dict(bands=[float('nan')]*32),
    dict(amplitude=float('inf')), dict(silence_progress=-.1), dict(speech_active=1)])
def test_unmeasurable_or_malformed_telemetry_fails_closed(changes):
    data=dict(amplitude=0., bands=[0.]*32, speech_active=False, silence_progress=0.)
    data.update(changes)
    with pytest.raises(ValidationError): VoiceMeterV1.model_validate(data)
