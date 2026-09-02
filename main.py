#!/usr/bin/env python3
"""
DCGP.AI CIRQ Governed Quantum Service
Atlasaurus Rex P3Q — toroidal flow inhabited runtime
Authority: Joshua L. Lopez / DCGP.AI LLC — USPTO 19/555,951
Routes through QUIRQ firewall. Not a public endpoint.
"""
import json
import sys
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
try:
    from dcgp.atlasaurus_rex_p3q_runtime_LOCKED import AtlasaurusRexP3QRuntime, demonstration_frame, RuntimeConfig
    HAS_ATLASAURUS = True
except ImportError:
    HAS_ATLASAURUS = False
app = FastAPI(title="DCGP CIRQ Governed Quantum Service", version="1.0.0")
_runtime = AtlasaurusRexP3QRuntime() if HAS_ATLASAURUS else None
@app.get("/health")
async def health():
    return {"ok": True, "service": "atlasaurus-rex-p3q", "has_atlasaurus": HAS_ATLASAURUS, "authority": "Joshua L. Lopez / DCGP.AI LLC", "patent": "USPTO 19/555,951"}
@app.post("/tick")
async def tick(request: Request):
    if not _runtime:
        return JSONResponse(content={"ok": False, "error": "atlasaurus_not_loaded"}, status_code=503)
    try:
        frame = await request.json()
    except Exception:
        frame = demonstration_frame()
    patent_facing = frame.pop("patent_facing", False)
    result = _runtime.tick_with_recovery(frame, patent_facing)
    return JSONResponse(content=result)
@app.post("/tick/demo")
async def tick_demo():
    if not _runtime:
        return JSONResponse(content={"ok": False, "error": "atlasaurus_not_loaded"}, status_code=503)
    result = _runtime.tick_with_recovery(demonstration_frame())
    return JSONResponse(content=result)
@app.get("/status")
async def status():
    return {"ok": True, "cycle": _runtime.cycle if _runtime else 0, "previous_receipt_hash": _runtime.previous_receipt_hash if _runtime else None, "service": "atlasaurus-rex-p3q-toroidal-flow", "authority": "Joshua L. Lopez / DCGP.AI LLC"}
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

