"""pluma.perception.ocr_adapter — On-demand OCR worker interface (stub).

Spec §8.3: PaddleOCR tiny/small models via ONNX Runtime.
Must NOT import PaddleOCR or ONNX Runtime at module level (idle runtime law).
Implemented in Phase 8.
"""


class OcrAdapter:
    """Stub: on-demand OCR worker. Implemented in Phase 8."""

    def run(self, image_bytes: bytes):  # type: ignore[return]
        raise NotImplementedError("OcrAdapter not implemented until Phase 8.")
