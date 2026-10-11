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
import hashlib
import hmac
import math
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeout
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

BACKEND_URL = os.environ.get("GOVERNED_BACKEND_URL", "").rstrip("/")
ROUTE_TIMEOUT = max(2.0, float(os.environ.get("CIRQ_ROUTE_TIMEOUT", "18")))
GLOBAL_INFERENCE_TIMEOUT = max(3.0, float(os.environ.get("CIRQ_GLOBAL_INFERENCE_TIMEOUT", "20")))
P3Q_TRANSPORT_KEY = os.environ.get("JETBASE_P3Q_TRANSPORT_KEY", "").strip()
_cap22_slots = threading.BoundedSemaphore(2)

app = FastAPI(title="DCGP CIRQ Governed Quantum Service", version="1.2.0")


def _call_backend(path: str, method: str = "GET", payload=None, timeout: float = 30):
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
        with urlrequest.urlopen(req, timeout=timeout) as response:
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
    import numpy as np

    # CAP-22 retrofit: preserve the original two-wire idea, but each wire is
    # an 11-qubit HOT rail. The dense statevector is therefore 22 qubits
    # (2^22 amplitudes), not the 1740Q outer GridQ/MPS register.
    GOV_ANGLE = 1.941611038725467
    PHI_RESTORING = 0.1
    CAPACITOR_PHASE = math.pi / 4.0
    SHOTS = 64

    digest = hashlib.sha256(message.encode("utf-8")).digest()
    seed = int.from_bytes(digest[:4], "big")

    h_minus = list(cirq.LineQubit.range(0, 11))
    h_plus = list(cirq.LineQubit.range(11, 22))
    qubits = h_minus + h_plus
    circuit = cirq.Circuit()

    # 11 HOT on each rail: X -> H -> RZ(pi/phi).
    for q in qubits:
        circuit.append(cirq.X(q))
        circuit.append(cirq.H(q))
        circuit.append(cirq.rz(GOV_ANGLE).on(q))

    # Dual cross-rail CX seat from the existing CAP-22 manifest.
    circuit.append(cirq.CNOT(h_minus[0], h_plus[0]))
    circuit.append(cirq.CNOT(h_plus[0], h_minus[0]))

    # capacitor_gate_1(CAPACITOR_PHASE) q11[0], q22_ext[0]
    circuit.append(cirq.rz(CAPACITOR_PHASE).on(h_minus[0]))
    circuit.append(cirq.CNOT(h_minus[0], h_plus[0]))
    circuit.append(cirq.rz(-CAPACITOR_PHASE).on(h_plus[0]))
    circuit.append(cirq.CNOT(h_minus[0], h_plus[0]))
    circuit.append(cirq.rz(CAPACITOR_PHASE).on(h_plus[0]))

    # capacitor_gate_2(CAPACITOR_PHASE) q22_ext[0], q11[0]
    circuit.append(cirq.ry(CAPACITOR_PHASE).on(h_plus[0]))
    circuit.append(cirq.CZ(h_plus[0], h_minus[0]))
    circuit.append(cirq.ry(-CAPACITOR_PHASE).on(h_minus[0]))
    circuit.append(cirq.CZ(h_plus[0], h_minus[0]))
    circuit.append(cirq.ry(CAPACITOR_PHASE).on(h_minus[0]))

    # Ring coupling on each 11-qubit HOT rail.
    for i in range(10):
        circuit.append(cirq.CZ(h_minus[i], h_minus[i + 1]))
        circuit.append(cirq.CZ(h_plus[i], h_plus[i + 1]))
    circuit.append(cirq.CZ(h_minus[10], h_minus[0]))
    circuit.append(cirq.CZ(h_plus[10], h_plus[0]))

    # Restoring pass on all 22 HOT qubits.
    for q in qubits:
        circuit.append(cirq.rx(PHI_RESTORING).on(q))

    simulator = cirq.Simulator(dtype=np.complex64, seed=seed)
    sim_result = simulator.simulate(circuit, qubit_order=qubits)
    state = sim_result.final_state_vector

    # Sample directly from the computed 22Q statevector so we do not run a
    # second state evolution just to obtain a compact receipt.
    samples = cirq.sample_state_vector(
        state,
        indices=list(range(22)),
        repetitions=SHOTS,
        seed=seed,
    )
    counts = {}
    for row in samples:
        bitstring = "".join(str(int(bit)) for bit in row)
        counts[bitstring] = counts.get(bitstring, 0) + 1

    norm = float(np.vdot(state, state).real)
    marginals = [float(np.mean(samples[:, i])) for i in range(6)]
    return {
        "engine": "cirq",
        "mode": "CIRQ_CAP22_TWIN_RAIL_STATEVECTOR",
        "compiler": "CAP-22",
        "rails": {
            "H-": {"hot_qubits": 11, "indices": [0, 10]},
            "H+": {"hot_qubits": 11, "indices": [11, 21]},
        },
        "active_qubits": 22,
        "statevector_amplitudes": int(state.size),
        "statevector_bytes": int(state.nbytes),
        "statevector_norm": norm,
        "outer_register": {
            "qubits": 1740,
            "dense_statevector": False,
            "role": "GridQ/MPS/addressing/governance",
        },
        "shots": SHOTS,
        "counts": counts,
        "six_data_marginals": marginals,
        "operation_count": sum(1 for _ in circuit.all_operations()),
        "input_hash": hashlib.sha256(message.encode("utf-8")).hexdigest(),
    }


def _bridge_authorized(request: Request):
    provided = request.headers.get("x-aura-bridge-key", "")
    return bool(P3Q_TRANSPORT_KEY and provided and hmac.compare_digest(provided, P3Q_TRANSPORT_KEY))

@app.post("/governance/sweep")
def governance_sweep(payload: dict, request: Request):
    if not _bridge_authorized(request):
        return JSONResponse(content={"ok":False,"error":"p3q_transport_authority_required"},status_code=403)
    code,data=_call_backend('/governance/sweep','POST',payload,timeout=900)
    return JSONResponse(content=data,status_code=code)


@app.post("/mc290/dense-rail/accept")
def mc290_dense_rail_accept(payload: dict, request: Request):
    if not _bridge_authorized(request):
        return JSONResponse(content={"ok": False, "error": "p3q_transport_authority_required"}, status_code=403)
    code, data = _call_backend("/mc290/dense-rail/accept", "POST", payload, timeout=900)
    return JSONResponse(content=data, status_code=code)


@app.post("/cap22/statevector")
def cap22_statevector(payload: dict, request: Request):
    if not _bridge_authorized(request):
        return JSONResponse(content={"ok": False, "error": "p3q_transport_authority_required"}, status_code=403)
    message = _extract_message(payload).strip()
    if not message or len(message) > 6000:
        return JSONResponse(content={"ok": False, "error": "message_required_max_6000_characters"}, status_code=400)
    with _cap22_slots:
        receipt = _cirq_inference_receipt(message)
    return {"ok": True, **receipt, "physical_claim": False}


@app.post("/intake/gguf")
def intake_gguf(packet: dict, request: Request):
    if not _bridge_authorized(request):
        return JSONResponse(content={"ok": False, "error": "p3q_transport_authority_required"}, status_code=403)
    cap22 = packet.get("cap22", {})
    probabilities = cap22.get("six_data_marginals")
    gguf = packet.get("gguf", [])
    if packet.get("oracle", {}).get("listener_port") != 14700 or not isinstance(probabilities, list) or len(probabilities) != 6 or any(
        isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not 0 <= v <= 1 for v in probabilities
    ) or not isinstance(gguf, list) or not gguf or any(not isinstance(g, dict) or not g.get("function") for g in gguf):
        return JSONResponse(content={"ok": False, "error": "measured_cap22_and_actual_gguf_receipts_required"}, status_code=400)
    norm = cap22.get("statevector_norm")
    counts = cap22.get("counts", {})
    valid_counts = isinstance(counts, dict) and bool(counts) and all(
        isinstance(bits, str) and len(bits) == 22 and set(bits) <= {'0', '1'} and isinstance(n, int) and not isinstance(n, bool) and n > 0
        for bits, n in counts.items()
    ) and sum(counts.values()) == 64
    if cap22.get("active_qubits") != 22 or cap22.get("shots") != 64 or not isinstance(norm, (int, float)) or not math.isfinite(norm) or abs(norm - 1.0) > 1e-4 or not valid_counts or any(
        abs(probabilities[i] - sum(n for bits, n in counts.items() if bits[i] == '1') / 64) > 1e-12 for i in range(6)
    ):
        return JSONResponse(content={"ok": False, "error": "normalized_cap22_receipt_required"}, status_code=400)
    canonical = json.dumps(packet, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    packet_hash = hashlib.sha256(canonical.encode()).hexdigest()
    seed = int(packet_hash[:8], 16)
    # Carry actual CAP-22 measured marginals into the existing private 9Q QHP
    # preparation. The original QHP measurement-to-P3Q mapping and locked
    # transition kernel remain the sole authority for admission and commitment.
    code, native = _call_backend("/qhp/decoherence-fuel/fire", "POST", {
        "coins": 1, "folds": 22, "shots": 256, "seed": seed, "body": probabilities, "include_svg": False
    }, timeout=900)
    if code >= 400 or native.get("ok") is not True:
        return JSONResponse(content={"ok": False, "error": native.get("error", "native_p3q_evaluation_incomplete"), "committed": False, "native": native}, status_code=code if code >= 400 else 502)
    receipts = [coin.get("receipt", {}) for coin in native.get("coins", [])]
    if not receipts or any(not receipt.get("receipt_hash") or not receipt.get("evaluation_complete") for receipt in receipts):
        return JSONResponse(content={"ok": False, "error": "complete_native_p3q_receipts_required", "committed": False}, status_code=502)
    return {
        "ok": True, "mode": "CAP22_GGUF_QHP_P3Q", "committed": all(receipt.get("committed") is True for receipt in receipts),
        "packet_sha256": packet_hash, "native_p3q": native, "receipts": receipts,
        "oracle": packet["oracle"], "position": packet.get("position"), "ohm": packet.get("ohm"),
        "cap22": cap22, "cirq_11q": packet.get("cirq_11q"), "circ": packet.get("circ"),
        "gguf": gguf, "frame": packet.get("frame"),
        "measured_bridge": {"source": "CAP-22 first six sampled wires", "six_data_marginals": probabilities, "qhp_qubits": 9, "qhp_shots": 256},
        "physical_claim": False
    }

def _inference_targets():
    targets = []
    for key, path in (
        ("VENUS_INFERENCE_URL", "/api/venus-inference"),
        # Permanent local-language cord: Aura115 /api/aura-voice talks directly
        # to the already-running GGUF listener and does not depend on /brain.
        ("GGUF_INFERENCE_URL", "/api/aura-voice"),
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
    started = time.monotonic()
    try:
        with urlrequest.urlopen(req, timeout=ROUTE_TIMEOUT) as response:
            raw = response.read().decode("utf-8")
            try:
                data = json.loads(raw) if raw else {}
            except Exception:
                data = {"ok": False, "reply": raw}
            return response.status, data, int((time.monotonic() - started) * 1000)
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(raw) if raw else {}
        except Exception:
            data = {"ok": False, "reply": raw}
        return exc.code, data, int((time.monotonic() - started) * 1000)
    except (URLError, TimeoutError, OSError):
        return 503, {"ok": False}, int((time.monotonic() - started) * 1000)


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

    targets = _inference_targets()
    if targets:
        executor = ThreadPoolExecutor(max_workers=len(targets), thread_name_prefix="cirq-route")
        futures = {
            executor.submit(_call_url, url, routed_payload): (route_name, url)
            for route_name, url in targets
        }
        deadline = time.monotonic() + GLOBAL_INFERENCE_TIMEOUT
        try:
            for future in as_completed(futures, timeout=GLOBAL_INFERENCE_TIMEOUT):
                route_name, _ = futures[future]
                try:
                    status, data, elapsed_ms = future.result()
                except Exception:
                    status, data, elapsed_ms = 503, {"ok": False}, 0
                reply = _usable_reply(data)
                attempts.append({
                    "route": route_name,
                    "status": status,
                    "answered": bool(reply),
                    "elapsed_ms": elapsed_ms,
                })
                if reply:
                    for pending in futures:
                        if pending is not future:
                            pending.cancel()
                    executor.shutdown(wait=False, cancel_futures=True)
                    return {
                        "ok": True,
                        "service": "cirq",
                        "mode": "CIRQ_INFERENCE_MESH",
                        "provider": route_name.lower(),
                        "reply": reply,
                        "response": reply,
                        "cirq_inference": receipt,
                        "attempts": attempts,
                        "governed": True,
                    }
                if time.monotonic() >= deadline:
                    break
        except FuturesTimeout:
            pass
        finally:
            for pending, (route_name, _) in futures.items():
                if not pending.done():
                    pending.cancel()
                    attempts.append({
                        "route": route_name,
                        "status": 504,
                        "answered": False,
                        "elapsed_ms": int(GLOBAL_INFERENCE_TIMEOUT * 1000),
                    })
            executor.shutdown(wait=False, cancel_futures=True)

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

