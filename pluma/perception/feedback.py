"""Transient observation metadata, never image/text content or action authority.

This packet records observations only. A native consumer MUST revalidate the
target before presentation; reading these facts performs no OS/capture work.
"""
from datetime import datetime,timezone
import hashlib
import threading
import time
from typing import Literal
from uuid import UUID

from pydantic import BaseModel,ConfigDict,Field,StrictBool,StrictFloat,StrictInt,StrictStr,model_validator


def canonical(value):
    if str(UUID(value))!=value:raise ValueError('Canonical observation identity required.')
    return value


def title_hash(value):return 'sha256:'+hashlib.sha256(value.encode('utf-8')).hexdigest()


class Bounds(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,frozen=True)
    left:StrictInt=Field(ge=-2147483648,le=2147483647)
    top:StrictInt=Field(ge=-2147483648,le=2147483647)
    right:StrictInt=Field(ge=-2147483648,le=2147483647)
    bottom:StrictInt=Field(ge=-2147483648,le=2147483647)

    @model_validator(mode='after')
    def positive(self):
        if self.right<=self.left or self.bottom<=self.top:raise ValueError('Empty target bounds.')
        return self

    def contains(self,other):
        return self.left<=other.left and self.top<=other.top and other.right<=self.right and other.bottom<=self.bottom


class Match(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,frozen=True)
    element_id:StrictStr
    bounds:Bounds
    confidence:StrictFloat=Field(ge=0,le=1,allow_inf_nan=False)

    @model_validator(mode='after')
    def identity(self):canonical(self.element_id);return self


class Evidence(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,frozen=True)
    observation_id:StrictStr
    snapshot_id:StrictStr
    hwnd:StrictInt=Field(gt=0,le=9223372036854775807)
    pid:StrictInt=Field(gt=0,le=2147483647)
    creation_time:StrictInt=Field(gt=0,le=9223372036854775807)
    window_class:StrictStr=Field(min_length=1,max_length=256)
    title_hash:StrictStr=Field(pattern=r'^sha256:[0-9a-f]{64}$')
    window_bounds:Bounds
    dpi_scale:StrictFloat=Field(ge=.25,le=8,allow_inf_nan=False)
    region:Bounds
    observed_utc:StrictStr=Field(max_length=64)
    expires_utc:StrictStr=Field(max_length=64)
    match_state:Literal['NOT_REQUESTED','NONE','UNIQUE','AMBIGUOUS']
    match:Match|None
    requires_target_revalidation:StrictBool=True

    @model_validator(mode='after')
    def consistent(self):
        canonical(self.observation_id);canonical(self.snapshot_id)
        if not self.requires_target_revalidation:raise ValueError('Observation is not presentation authority.')
        start=datetime.fromisoformat(self.observed_utc);end=datetime.fromisoformat(self.expires_utc)
        if (start.utcoffset() is None or end.utcoffset() is None or start.utcoffset().total_seconds()!=0
                or end.utcoffset().total_seconds()!=0 or not 0<(end-start).total_seconds()<=3):
            raise ValueError('Invalid observation lifetime.')
        local=Bounds(left=0,top=0,right=self.window_bounds.right-self.window_bounds.left,
                     bottom=self.window_bounds.bottom-self.window_bounds.top)
        if not local.contains(self.region) or (self.match_state=='UNIQUE')!=(self.match is not None):
            raise ValueError('Inconsistent observation geometry or match.')
        if self.match is not None and not self.region.contains(self.match.bounds):raise ValueError('Match outside captured region.')
        return self


class Observation(Evidence):
    task_id:StrictStr
    task_request_id:StrictStr
    sequence:StrictInt=Field(gt=0)

    @model_validator(mode='after')
    def task(self):canonical(self.task_id);canonical(self.task_request_id);return self


class PerceptionFeedback:
    def __init__(self):
        self._lock=threading.Lock();self._item=None;self._deadline=0;self._sequence=0

    def clear(self):
        with self._lock:self._item=None;self._deadline=0

    def publish(self,receipt,cap):
        """Admit only metadata anchored to this task's actual snapshot registry."""
        evidence=Evidence.model_validate(receipt)
        snapshot=cap.snapshot_registry.resolve_bounded(evidence.snapshot_id)
        if (snapshot.hwnd!=evidence.hwnd or snapshot.pid!=evidence.pid or snapshot.window_class!=evidence.window_class
                or title_hash(snapshot.active_window_title)!=evidence.title_hash
                or snapshot.window_rect.model_dump()!=evidence.window_bounds.model_dump()
                or snapshot.dpi_scale!=evidence.dpi_scale):raise ValueError('Observation target mismatch.')
        if evidence.match is not None:
            candidates=[e for e in snapshot.ocr_words if e.element_id==evidence.match.element_id]
            if (len(candidates)!=1 or candidates[0].source.value!='OCR' or candidates[0].snapshot_id!=snapshot.snapshot_id
                    or candidates[0].bounds.model_dump()!=evidence.match.bounds.model_dump() or candidates[0].confidence!=evidence.match.confidence):
                raise ValueError('Observation match is not in the task snapshot.')
        expiry=datetime.fromisoformat(evidence.expires_utc)
        remaining=min(3.,(expiry-datetime.now(timezone.utc)).total_seconds(),
                      (snapshot.expires_at-datetime.now(timezone.utc)).total_seconds())
        if remaining<=0:return
        with self._lock:
            if cap.stop_latch_set or cap.state.value!='RUNNING':return
            self._sequence+=1
            self._item=Observation(**evidence.model_dump(),task_id=cap.task_id,task_request_id=cap.request_id,sequence=self._sequence)
            self._deadline=time.monotonic()+remaining

    def snapshot(self,cap):
        if not self._lock.acquire(timeout=.02):raise TimeoutError('Perception readback is busy.')
        try:
            if (cap.stop_latch_set or cap.state.value!='RUNNING' or time.monotonic()>=self._deadline
                    or self._item is not None and datetime.now(timezone.utc)>=datetime.fromisoformat(self._item.expires_utc)):
                self._item=None;return None
            if self._item is not None:
                try:cap.snapshot_registry.resolve_bounded(self._item.snapshot_id)
                except TimeoutError:raise
                except Exception:self._item=None
            return self._item
        finally:self._lock.release()
