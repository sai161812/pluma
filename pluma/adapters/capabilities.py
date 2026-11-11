"""Explicit setup probes. No downloads, inference, screenshots or audio storage."""
import importlib.metadata
import os
from pathlib import Path


def _model(path, magic, module):
    path=Path(path)
    if not path.is_absolute() or str(path).startswith(("\\\\","//")):
        raise ValueError("LOCAL_FILE_REQUIRED")
    before=path.stat()
    with path.open("rb") as stream:
        if stream.read(4)!=magic or not stream.read(4):raise ValueError("MODEL_FORMAT_UNAVAILABLE")
    import gc,weakref
    if module=="llama_cpp":
        from llama_cpp import Llama
        native=Llama(model_path=str(path),vocab_only=True,n_ctx=32,n_gpu_layers=0,verbose=False)
        native.close()
        native=None
    else:
        from pywhispercpp.model import Model,pw
        native=Model(str(path),n_threads=2,redirect_whispercpp_logs_to=None,
                     print_realtime=False,print_progress=False,print_timestamps=False)
        reference=weakref.ref(native)
        pw.assign_new_segment_callback(native._params,None)
        pw.assign_abort_callback(native._params,None)
        native._new_segment_callback=None
        native=None;gc.collect()
        if reference() is not None:raise RuntimeError("STT_RELEASE_UNVERIFIED")
    after=path.stat()
    if (before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_ino,after.st_size,after.st_mtime_ns):
        raise ValueError("MODEL_CHANGED")


def probe(name, config, microphone_consent):
    if name=="planner":
        _model(config["planner"],b"GGUF","llama_cpp")
    elif name=="speech":
        _model(config["speech"],b"lmgg","pywhispercpp.model")
    elif name=="ocr":
        importlib.metadata.version("paddleocr")
        import onnxruntime
        if "CPUExecutionProvider" not in onnxruntime.get_available_providers():raise RuntimeError("OCR_CPU_UNAVAILABLE")
        from pluma.perception.ocr_adapter import _PADDLEOCR_DETECTION_MODEL,_PADDLEOCR_RECOGNITION_MODEL
        for model in (_PADDLEOCR_DETECTION_MODEL,_PADDLEOCR_RECOGNITION_MODEL):
            folder=Path(config["ocr"])/(model+"_onnx")
            if not folder.is_dir():folder=Path(config["ocr"])/model
            if not folder.is_dir():raise FileNotFoundError("OCR_LOCAL_FILES_UNAVAILABLE")
            if not (folder/"inference.yml").is_file():raise FileNotFoundError("OCR_CONFIG_UNAVAILABLE")
            onnx_files=list(folder.rglob("*.onnx"))
            if not onnx_files or len(onnx_files)>16:raise FileNotFoundError("OCR_ONNX_FILES_UNAVAILABLE")
            import weakref,gc
            options=onnxruntime.SessionOptions();options.intra_op_num_threads=2;options.inter_op_num_threads=1
            session=onnxruntime.InferenceSession(str(onnx_files[0]),sess_options=options,providers=["CPUExecutionProvider"])
            if not session.get_inputs() or not session.get_outputs():raise RuntimeError("OCR_SESSION_UNAVAILABLE")
            reference=weakref.ref(session);session=None;gc.collect()
            if reference() is not None:raise RuntimeError("OCR_RELEASE_UNVERIFIED")
    elif name=="uia":
        from pywinauto.uia_defines import IUIA
        automation=IUIA().iuia
        if automation.GetRootElement() is None:raise RuntimeError("UIA_UNAVAILABLE")
        del automation
    elif name=="microphone":
        if not microphone_consent:return "UNVERIFIED","MICROPHONE_CONSENT_REQUIRED"
        import sounddevice
        # No buffer/callback retains samples. Open/start/close tests actual access.
        stream=sounddevice.RawInputStream(samplerate=16000,channels=1,dtype="int16",
            callback=lambda _data,_frames,_time,_status:None)
        try:
            stream.start()
            if not stream.active:raise RuntimeError("MICROPHONE_NOT_ACTIVE")
        finally:
            stream.close()
        if not stream.closed:raise RuntimeError("MICROPHONE_CLOSE_UNVERIFIED")
    else:raise ValueError("UNKNOWN_CAPABILITY")
    return "PASSED","NATIVE_ACCESS_VERIFIED"


def check_setup(config, consent, token):
    checks=[]
    for name in ("planner","speech","ocr","uia","microphone"):
        token.raise_if_cancelled()
        try:state,code=probe(name,config,consent)
        except Exception:state,code="FAILED",name.upper()+"_UNAVAILABLE"
        checks.append({"id":name,"state":state,"code":code,"origin":"native"})
    token.raise_if_cancelled()
    return checks
