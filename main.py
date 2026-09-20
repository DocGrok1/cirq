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



def _extract_message(payload):
    payload = payload or {}
    if isinstance(payload, dict):
        for key in ("message", "input", "prompt", "text"):
            value = payload.get(key)
            if value:
                return str(value)
        msgs = payload.get("messages")
        if isinstance(msgs, list):
            for item in reversed(msgs):
                if isinstance(item, dict) and item.get("role") == "user" and item.get("content"):
                    return str(item["content"])
    return ""


def _cirq_inference_receipt(message: str):
    import cirq
    import hashlib
    import math

    digest = hashlib.sha256(message.encode("utf-8")).digest()
    q0, q1 = cirq.LineQubit.range(2)
    phase_a = (digest[0] / 255.0) * math.pi
    phase_b = (digest[1] / 255.0) * math.pi
    circuit = cirq.Circuit(
        cirq.H(q0),
        cirq.CNOT(q0, q1),
        cirq.rz(phase_a).on(q0),
        cirq.rx(phase_b).on(q1),
        cirq.measure(q0, q1, key="m"),
    )
    result = cirq.Simulator(seed=int.from_bytes(digest[:4], "big")).run(circuit, repetitions=64)
    counts = {str(k): int(v) for k, v in result.histogram(key="m").items()}
    return {
        "engine": "cirq",
        "mode": "CIRQ_INFERENCE",
        "circuit": str(circuit),
        "shots": 64,
        "counts": counts,
        "input_hash": hashlib.sha256(message.encode("utf-8")).hexdigest(),
    }


def _inference_targets():
    targets = []
    for key, path in (
        ("VENUS_INFERENCE_URL", "/api/venus-inference"),
        ("AURA116_INFERENCE_URL", "/api/webb-inference"),
        ("CLAUDIA_INFERENCE_URL", "/api/governed-claude-chat"),
    ):
        base = os.environ.get(key, "").rstrip("/")
        if base:
            targets.append((key, base + path))
    return targets


def _call_url(url: str, payload):
    body = json.dumps(payload).encode("utf-8")
    req = urlrequest.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "x-aura-source": "cirq-inference"},
        method="POST",
    )
    try:
        with urlrequest.urlopen(req, timeout=35) as response:
            raw = response.read().decode("utf-8")
            try:
                return response.status, json.loads(raw) if raw else {}
            except Exception:
                return response.status, {"ok": False, "reply": raw}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw) if raw else {}
        except Exception:
            return exc.code, {"ok": False, "reply": raw}
    except (URLError, TimeoutError, OSError):
        return 503, {"ok": False}


def _usable_reply(data):
    if not isinstance(data, dict):
        return ""
    reply = data.get("reply") or data.get("response") or data.get("text") or data.get("output") or ""
    text = str(reply).strip()
    bad = ("all inference routes exhausted", "governance failure", "inference initializing")
    if not text or any(x in text.lower() for x in bad):
        return ""
    return text


@app.post("/inference")
async def inference(request: Request):
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    message = _extract_message(payload)
    if not message:
        return JSONResponse(content={"ok": False, "error": "message_required"}, status_code=400)

    receipt = _cirq_inference_receipt(message)
    attempts = []
    routed_payload = dict(payload) if isinstance(payload, dict) else {}
    routed_payload.update({
        "message": message,
        "prompt": message,
        "cirq_inference": receipt,
        "source": "cirq-production-inference",
    })

    for route_name, url in _inference_targets():
        status, data = _call_url(url, routed_payload)
        reply = _usable_reply(data)
        attempts.append({"route": route_name, "status": status, "answered": bool(reply)})
        if reply:
            return {
                "ok": True,
                "service": "cirq",
                "mode": "CIRQ_INFERENCE_ROUTER",
                "provider": route_name.lower(),
                "reply": reply,
                "response": reply,
                "cirq_inference": receipt,
                "attempts": attempts,
                "governed": True,
            }

    return JSONResponse(
        content={
            "ok": False,
            "service": "cirq",
            "mode": "CIRQ_INFERENCE_ROUTER",
            "reply": "All inference routes exhausted.",
            "response": "All inference routes exhausted.",
            "cirq_inference": receipt,
            "attempts": attempts,
            "governed": True,
        },
        status_code=503,
    )


@app.post("/run")
async def run_inference(request: Request):
    return await inference(request)


@app.post("/v1/chat/completions")
async def openai_compat(request: Request):
    result = await inference(request)
    if isinstance(result, JSONResponse):
        return result
    reply = result.get("reply", "")
    return {
        "id": "cirq-production",
        "object": "chat.completion",
        "model": "cirq-venus-governed",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": reply}, "finish_reason": "stop"}],
        "cirq_inference": result.get("cirq_inference"),
        "attempts": result.get("attempts"),
    }

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
