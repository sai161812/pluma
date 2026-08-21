# PLUMA Technology Contract

This file is a concise implementation reference. The complete requirements and
limitations remain in `PLUMA_MASTER_SPEC.md`.

```text
Target OS: Windows 11
Core: Python 3.12+
Windows native access: ctypes + pywin32
Desktop automation: pywinauto, Microsoft UI Automation (UIA)
Voice capture: sounddevice + VAD
Speech-to-text: whisper.cpp, quantized local Whisper model
Voice output: Windows SAPI through pywin32/comtypes
Screen capture: target-window/region capture using a lightweight Windows adapter
OCR: PaddleOCR tiny/small models through ONNX Runtime
Planner runtime: llama.cpp through a replaceable adapter
Planner model: benchmark-selected small local instruction model (initial Qwen3-4B GGUF Q4_K_M)
Structured output: JSON Schema or GBNF grammar plus second-pass validation
Schemas: Pydantic and/or jsonschema
Persistence: SQLite with a controlled writer; WAL is acceptable
IPC: local-only named pipe or localhost equivalent
Process ownership: Windows Job Objects
System scripting: controlled PowerShell subprocess wrapper
Packaging: PyInstaller or Nuitka for V1; evaluate MSIX later
Tests: pytest and deterministic Windows fixture applications/scripts
```

## Dependency boundary

Code outside adapters and perception workers must not import pywinauto classes,
OCR-library objects, PowerShell implementation details or a specific model
library directly. All of those dependencies must be replaceable behind an
interface.

## Runtime boundary

```text
IDLE:
  resident core, hotkeys, STOP listener, tray/IPC, task guard

LISTENING:
  microphone, VAD, STT only as required

FAST ACTIVE:
  deterministic router, tool, verifier

SCREEN ACTIVE:
  UIA and targeted capture/OCR only when necessary

SMART ACTIVE:
  local planner plus route-specific tools/context

STOPPING:
  cancellation, rollback, cleanup and verification only
```
