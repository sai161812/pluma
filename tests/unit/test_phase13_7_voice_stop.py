"""tests.unit.test_phase13_7_voice_stop — Verify STOP cancels voice capture and STT cleanly."""

import time
import pytest
from typing import Optional

from pluma.core.cancellation import CancellationToken
from pluma.core.resident import ResidentCore
from pluma.core.task_supervisor import TaskState

class MockAudioCapture:
    def __init__(self):
        self.started = False
    def start(self):
        self.started = True
    def stop_and_get(self):
        self.started = False
        return b"\x00" * 32000  # 1 second of silent audio

class MockVoicePipeline:
    def process_audio(self, raw_audio, cancellation_token: Optional[CancellationToken] = None):
        # Simulate STT taking some time, during which STOP might be hit
        if cancellation_token and cancellation_token.is_cancelled:
            return None
        return None

def test_stop_during_voice_capture():
    resident = ResidentCore()
    resident.audio_capture = MockAudioCapture()
    resident.voice_pipeline = MockVoicePipeline()
    
    # 1. User presses hotkey
    resident._on_voice_press()
    assert resident.audio_capture.started is True
    
    capsule = resident._current_voice_capsule
    assert capsule is not None
    assert capsule.state == TaskState.CREATED
    
    # 2. User presses STOP
    resident.supervisor.stop_task(capsule.task_id)
    assert capsule.cancellation_token.is_cancelled is True
    assert capsule.state == TaskState.STOPPED
    
    # 3. User releases hotkey
    resident._on_voice_release()
    
    # Task should not proceed
    assert resident.audio_capture.started is False
    assert capsule.state == TaskState.STOPPED


def test_stop_during_stt():
    resident = ResidentCore()
    resident.audio_capture = MockAudioCapture()
    
    class SlowPipeline:
        def process_audio(self, raw_audio, cancellation_token=None):
            resident.supervisor.stop_task(resident._current_voice_capsule.task_id)
            if cancellation_token and cancellation_token.is_cancelled:
                return None
            return None
            
    resident.voice_pipeline = SlowPipeline()
    
    resident._on_voice_press()
    capsule = resident._current_voice_capsule
    resident._on_voice_release()
    
    assert capsule.cancellation_token.is_cancelled is True
    assert capsule.state == TaskState.STOPPED

