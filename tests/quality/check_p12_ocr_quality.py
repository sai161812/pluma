"""Run with the optional OCR environment; renders only generated text in memory.

This bounded P12 correctness sample is not the P26 application quality corpus.
Exit zero requires every generated line to be recovered exactly with valid bounds.
"""
from __future__ import annotations

import io
import json
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from pluma.perception.ocr_adapter import OcrAdapter


LABELS = ("Save Changes", "Cancel", "Settings", "Volume 20%", "report_v2.pdf",
          "Ctrl+Shift+S", "1,234.56", "Access denied")


def main() -> None:
    adapter = OcrAdapter()
    adapter.load()
    cases = []
    started = time.perf_counter()
    try:
        for family in ("segoeui.ttf", "arial.ttf"):
            for size in (12, 16, 22):
                for scale in (1.0, 1.25, 1.5):
                    for dark in (False, True):
                        width, height = round(940 * scale), round(440 * scale)
                        image = Image.new("RGB", (width, height), "#202020" if dark else "white")
                        draw = ImageDraw.Draw(image)
                        font = ImageFont.truetype(str(Path("C:/Windows/Fonts") / family), round(size * scale))
                        for index, label in enumerate(LABELS):
                            color = ("#86B7FF" if dark else "#174EA6") if index % 2 else ("white" if dark else "black")
                            draw.text((24 * scale, (15 + index * 52) * scale), label, font=font, fill=color)
                        buffer = io.BytesIO()
                        image.save(buffer, format="PNG")
                        result = adapter.run(buffer.getvalue())
                        actual = [word.text for word in result.words]
                        bounds_ok = all(0 <= word.bounds.left < word.bounds.right <= width
                            and 0 <= word.bounds.top < word.bounds.bottom <= height for word in result.words)
                        cases.append({"font": family, "size_px": size, "scale": scale, "dark": dark,
                            "exact_lines": sum(label in actual for label in LABELS),
                            "minimum_confidence": min((word.confidence for word in result.words), default=0),
                            "bounds_ok": bounds_ok, "duration_ms": result.duration_ms,
                            "unexpected": actual if actual != list(LABELS) else []})
    finally:
        adapter.unload()
    report = {"model": "PP-OCRv6_small_det/PP-OCRv6_small_rec", "engine": "ONNX Runtime CPU",
        "cases": len(cases), "exact_lines": sum(case["exact_lines"] for case in cases),
        "expected_lines": len(cases) * len(LABELS),
        "elapsed_inference_seconds": round(time.perf_counter() - started, 2),
        "bounds_valid": all(case["bounds_ok"] for case in cases),
        "minimum_confidence": min(case["minimum_confidence"] for case in cases),
        "failures": [case for case in cases if case["unexpected"] or not case["bounds_ok"] or case["minimum_confidence"] < 0.9]}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    assert not report["failures"], "Generated UI-text recognition did not recover every expected line exactly."


if __name__ == "__main__":
    main()
