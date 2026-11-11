"""Explicit disposable-host model provisioning, never resident startup or tool execution."""
import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ['PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK']='True'
from paddleocr import PaddleOCR

engine=PaddleOCR(text_detection_model_name='PP-OCRv6_small_det',text_recognition_model_name='PP-OCRv6_small_rec',
    use_doc_orientation_classify=False,use_doc_unwarping=False,use_textline_orientation=False,
    device='cpu',engine='onnxruntime',engine_config={'onnxruntime':{'device_type':'cpu','providers':['CPUExecutionProvider']}})
from pluma.perception.ocr_adapter import _local_model_dirs
files=[]
for directory in _local_model_dirs():
    for name in ('inference.onnx','inference.yml'):
        path=directory/name
        files.append(dict(model=directory.name,file=name,sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
manifest={'provisioned_models':files,'provider':'CPUExecutionProvider'}
if len(sys.argv)>1:
    destination=Path(sys.argv[1]);destination.parent.mkdir(parents=True,exist_ok=True)
    with destination.open('x',encoding='utf-8') as stream:json.dump(manifest,stream,indent=2)
print(json.dumps(manifest))
del engine
