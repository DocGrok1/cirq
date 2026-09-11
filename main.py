#!/usr/bin/env python3
"""
DCGP.AI CIRQ Governed Quantum Service
Authority: Joshua L. Lopez / DCGP.AI LLC — USPTO 19/555,951

Public CIRQ service contract. Governed computation is reached only through the
private Railway service network. The private runtime implementation is not
embedded in this public service.
"""
from __future__ import annotations

import json
import os
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

BACKEND_URL = os.environ.get("GOVERNED_BACKEND_URL", "").rstrip("/")

app = FastAPI(title="DCGP CIRQ Governed Quantum Service", version="1.1.0")


def _call_backend(path: str, method: str = "GET", payload=None):
    if not BACKEND_URL:
        return 503, {"ok": False, "error": "governed_backend_not_configured"}

    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"} if body is not None else {}
    req = urlrequest.Request(
        BACKEND_URL + path,
        data=body,
        headers=headers,
        method=method,
    )

    try:
        with urlrequest.urlopen(req, timeout=30) as response:
            raw = response.read().decode("utf-8")
            try:
                data = json.loads(raw) if raw else {}
            except Exception:
                data = {"ok": False, "error": "invalid_governed_backend_response"}
            return response.status, data
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(raw) if raw else {}
        except Exception:
            data = {"ok": False, "error": "governed_backend_http_error"}
        return exc.code, data
    except (URLError, TimeoutError, OSError):
        return 503, {"ok": False, "error": "governed_backend_unreachable"}


@app.get("/health")
async def health():
    code, data = _call_backend("/health")
    if code >= 400:
        return JSONResponse(
            content={"ok": False, "service": "cirq", "governed_backend": False, "error": data.get("error", "unavailable")},
            status_code=code,
        )
    return {"ok": True, "service": "cirq", "governed_backend": True}


@app.get("/status")
async def status():
    code, data = _call_backend("/status")
    if code >= 400:
        return JSONResponse(
            content={"ok": False, "service": "cirq", "governed_backend": False, "error": data.get("error", "unavailable")},
            status_code=code,
        )
    return {
        "ok": True,
        "service": "cirq",
        "governed_backend": True,
        "cycle": data.get("cycle", 0),
        "previous_receipt_hash": data.get("previous_receipt_hash"),
    }


@app.post("/tick")
async def tick(request: Request):
    try:
        frame = await request.json()
    except Exception:
        frame = {}
    code, data = _call_backend("/tick", "POST", frame)
    return JSONResponse(content=data, status_code=code)


@app.post("/tick/demo")
async def tick_demo():
    code, data = _call_backend("/tick/demo", "POST", {})
    return JSONResponse(content=data, status_code=code)


if __name__ == "__main__":
    import uvicorn

    # Preserve the existing CIRQ Railway listen contract.
    uvicorn.run(app, host="0.0.0.0", port=8000)
