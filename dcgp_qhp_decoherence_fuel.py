#!/usr/bin/env python3
"""DCGP.AI QHP Decoherence-to-Fuel Fold Circuit.

Authority: Joshua L. Lopez / DCGP.AI LLC.
Protocol surface: QHP-1.0 / CEO-CVP-CCTP-v2 / NAME SVG.

The circuit models the user's fold law without modifying the private governed
Atlasaurus Rex runtime. Six data qubits are organized as three fold planes.
Each fold:
  1. applies the governed pair coupling,
  2. couples each plane to a reusable environment/syndrome qubit,
  3. measures that departure (the decoherence event),
  4. uses the measured residue as feed-forward control (fuel), and
  5. applies an idempotent parity projection back to the admissible S* code space.

The positive-definite metric remains an explicit governance invariant. The
quantum circuit supplies measurement receipts; the private P3Q service mints
MC290 coins from those receipts.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
import math
import os
from datetime import datetime, timezone
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError

import cirq
import numpy as np

AUTHORITY = "Joshua L. Lopez / DCGP.AI LLC"
PROTOCOL = "CEO-CVP-CCTP-v2"
QHP_VERSION = "QHP-1.0"
ECHO = "E:Sigma*->S*"
GOV_ANGLE = math.pi / ((1.0 + math.sqrt(5.0)) / 2.0)
METRIC_DIAGONAL = (1.0, 1.0, 1.0, 1.0, 1.0, 1.0)
PAIR_PLANES = ((0, 1), (2, 3), (4, 5))

PLANET_CODES = {
    "Mercury": "Me", "Venus": "Ve", "Earth": "Ea", "Mars": "Ma",
    "Jupiter": "Ju", "Saturn": "Sa", "Uranus": "Ur", "Neptune": "Ne",
    "Pluto": "Pl", "Moon": "Mo",
}
DOMAIN_CODES = {"quantum_governance": "qgv", "quantum_simulation": "qsm"}
STATUS_CODES = {"approved": "a", "active": "v", "rescued": "W", "held": "h"}


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_seed(name: str, offset: int = 0) -> int:
    value = int(_sha256_text(f"{name}:{offset}")[:8], 16)
    return (value + offset) & 0x7FFFFFFF


def qs1_name(obj: dict) -> str:
    ident = str(obj.get("coin_id") or obj.get("id") or obj.get("node_id") or "")
    digest = _sha256_text(json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str))
    checksum = np.base_repr(int(digest[:8], 16), base=36).upper().rjust(7, "0")
    planet = PLANET_CODES.get(obj.get("planet"), "Xx")
    domain = DOMAIN_CODES.get(str(obj.get("domain", "")).lower(), "gen")
    novelty = str(round(float(obj.get("novelty_score") or obj.get("novelty") or 0))).rjust(2, "0")
    return f"QS1|{ident[-8:]}|{planet}.{domain}.{novelty}|{checksum}"


def cvp_compress(obj: dict) -> dict:
    h_value = obj.get("H")
    gate = obj.get("gate") or {}
    if h_value is None:
        h_value = gate.get("H")
    return {
        "_v": "CVP2",
        "id": obj.get("coin_id") or obj.get("id") or obj.get("node_id"),
        "n": round(float(obj.get("novelty_score") or obj.get("novelty") or 0)),
        "H": None if h_value is None else round(float(h_value), 3),
        "p": PLANET_CODES.get(obj.get("planet"), obj.get("planet")),
        "d": DOMAIN_CODES.get(str(obj.get("domain", "")).lower(), str(obj.get("domain", ""))[:6]),
        "s": STATUS_CODES.get(obj.get("status"), obj.get("status")),
        "L": obj.get("lane") or obj.get("lane_num"),
        "N": obj.get("node") or obj.get("node_num"),
        "t": str(obj.get("minted_at") or obj.get("routed_at") or obj.get("written_at") or "")[:19],
    }


def ceo_compress(obj: dict) -> dict:
    cvp = cvp_compress(obj)
    gate = obj.get("gate") or {}
    cats = obj.get("categories") or ""
    if isinstance(cats, (list, tuple)):
        cats = ",".join(map(str, cats))
    return {
        "_v": "CEO2",
        **cvp,
        "qs1": qs1_name(obj),
        "ti": str(obj.get("title") or "")[:80],
        "g": gate.get("regime") or gate.get("status") or obj.get("regime"),
        "dr": round(float(gate.get("drift") or 0.0), 4),
        "cats": ",".join(x.strip()[:4] for x in str(cats).split(",") if x.strip()),
        "src": str(obj.get("source") or "")[:12],
        "pat": str(obj.get("patent_ref") or "").replace("USPTO ", ""),
        "_echo": ECHO,
    }


def cctp_encode(obj: dict) -> str:
    ceo = ceo_compress(obj)
    payload = json.dumps(ceo, separators=(",", ":"), sort_keys=True)
    digest = _sha256_text(payload)[:12]
    return f"CCTP|{digest}|{payload}"


def build_fold_circuit(folds: int = 22, seed_name: str = "DECOHERENCE-FUEL") -> cirq.Circuit:
    """Build one 6+3 qubit repeated governed fold circuit.

    The syndrome measurement is the decoherence event. Its classical bit controls
    the next admissible rotation, so discarded departure becomes feed-forward.
    The parity check/correction is a measurement projector; applying it again is
    idempotent on the admissible even-parity subspace.
    """
    folds = max(1, min(22, int(folds)))
    data = [cirq.LineQubit(i) for i in range(6)]
    anc = [cirq.LineQubit(6 + i) for i in range(3)]
    circuit = cirq.Circuit()

    digest = bytes.fromhex(_sha256_text(seed_name)[:12])
    for i, q in enumerate(data):
        angle = ((digest[i] / 255.0) - 0.5) * (math.pi / 2.0)
        circuit.append(cirq.ry(angle).on(q))
        circuit.append(cirq.H.on(q))

    for fold in range(folds):
        theta = GOV_ANGLE / (1.0 + 0.125 * fold)
        fuel_angle = GOV_ANGLE / (2.0 + fold)
        for plane, (i, j) in enumerate(PAIR_PLANES):
            a = anc[plane]
            q0, q1 = data[i], data[j]
            circuit.append([cirq.CNOT(q0, q1), cirq.rz(theta).on(q1), cirq.CNOT(q0, q1)])
            dkey = f"d{fold:02d}_{plane}"
            circuit.append(cirq.CNOT(q1, a))
            circuit.append(cirq.measure(a, key=dkey))
            circuit.append(cirq.rx(fuel_angle).on(q0).with_classical_controls(dkey))
            circuit.append(cirq.reset(a))
            pkey = f"p{fold:02d}_{plane}"
            circuit.append([cirq.CNOT(q0, a), cirq.CNOT(q1, a)])
            circuit.append(cirq.measure(a, key=pkey))
            circuit.append(cirq.X(q1).with_classical_controls(pkey))
            circuit.append(cirq.reset(a))

    circuit.append(cirq.measure(*data, key="final"))
    return circuit


def _mean_key(result: cirq.Result, key: str) -> float:
    arr = result.measurements.get(key)
    if arr is None or arr.size == 0:
        return 0.0
    return float(np.mean(arr.astype(np.float64)))


def run_fold_circuit(*, folds: int = 22, shots: int = 128, seed_name: str = "DECOHERENCE-FUEL", seed: int | None = None) -> dict:
    folds = max(1, min(22, int(folds)))
    shots = max(16, min(1024, int(shots)))
    seed = _stable_seed(seed_name) if seed is None else int(seed)
    circuit = build_fold_circuit(folds=folds, seed_name=seed_name)
    simulator = cirq.Simulator(seed=seed)
    result = simulator.run(circuit, repetitions=shots)

    d_keys = [f"d{k:02d}_{p}" for k in range(folds) for p in range(3)]
    p_keys = [f"p{k:02d}_{p}" for k in range(folds) for p in range(3)]
    fuel_density = float(np.mean([_mean_key(result, k) for k in d_keys])) if d_keys else 0.0
    projection_density = float(np.mean([_mean_key(result, k) for k in p_keys])) if p_keys else 0.0

    final = result.measurements["final"].astype(np.int8)
    means = np.mean(final, axis=0)
    state6 = [round(float((m - 0.5) * 0.20), 8) for m in means]

    pair_even = np.ones(final.shape[0], dtype=bool)
    for i, j in PAIR_PLANES:
        pair_even &= (final[:, i] == final[:, j])
    even_fraction = float(np.mean(pair_even))

    positive_definite = all(v > 0.0 for v in METRIC_DIAGONAL)
    no_horizon = positive_definite and even_fraction >= 0.99

    return {
        "engine": "DCGP.QHP.DECOHERENCE_FUEL_FOLD",
        "framework": "cirq",
        "qubits": 9,
        "data_qubits": 6,
        "syndrome_qubits": 3,
        "folds": folds,
        "shots": shots,
        "seed": seed,
        "governance_angle": GOV_ANGLE,
        "metric_diagonal": list(METRIC_DIAGONAL),
        "metric_positive_definite": positive_definite,
        "fuel_density": round(fuel_density, 8),
        "projection_correction_density": round(projection_density, 8),
        "equilibrium_even_parity_fraction": round(even_fraction, 8),
        "horizon_encountered": not no_horizon,
        "state6": state6,
        "measurement_key_count": len(d_keys) + len(p_keys) + 1,
        "law": "decoherence -> measured residue -> feed-forward fuel -> idempotent projection -> S*",
    }


def build_governed_frame(metrics: dict) -> dict:
    state = [float(v) for v in metrics["state6"]]
    fuel = max(0.05, float(metrics["fuel_density"]))
    faces = [1.0, 1.0, 1.0, 1.0, 1.0]
    z11 = state + faces
    decoherence_generators = []
    for axis in range(6):
        vec = [0.0] * 6
        vec[axis] = fuel
        decoherence_generators.append(vec)
    return {
        "state": state,
        "chvm": {
            "sustained_validity": True,
            "fidelity": float(metrics["equilibrium_even_parity_fraction"]) >= 0.99,
            "conservation": True,
            "continuity": True,
            "slow_memory_coupling": True,
        },
        "h_minus": z11,
        "h_plus": z11,
        "previous_return": 1.0,
        "current_return": min(0.80, 0.20 + fuel * 0.40),
        "governance_signal": [0.0] * 6,
        "decoherence_generators": decoherence_generators,
        "surplus_obligation": fuel,
        "obligation": 0.50,
        "capability": 0.80,
        "temporal_window": 1.0,
        "rescue_window": 0.0,
        "qhp_fold_receipt": {
            "folds": metrics["folds"],
            "fuel_density": metrics["fuel_density"],
            "metric_positive_definite": metrics["metric_positive_definite"],
            "horizon_encountered": metrics["horizon_encountered"],
        },
    }


def _call_backend(base_url: str, path: str, payload: dict) -> tuple[int, dict]:
    if not base_url:
        return 503, {"ok": False, "error": "governed_backend_not_configured"}
    req = urlrequest.Request(
        base_url.rstrip("/") + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlrequest.urlopen(req, timeout=45) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw) if raw else {}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(raw) if raw else {}
        except Exception:
            data = {"ok": False, "error": "governed_backend_http_error", "raw": raw[:500]}
        return exc.code, data
    except (URLError, TimeoutError, OSError) as exc:
        return 503, {"ok": False, "error": "governed_backend_unreachable", "detail": str(exc)}


def _coin_object(coin_id: str, metrics: dict, backend_receipt: dict, index: int) -> dict:
    status = "approved" if backend_receipt.get("admitted") else "held"
    return {
        "coin_id": coin_id,
        "id": coin_id,
        "novelty_score": 100,
        "H": 0.0,
        "planet": "Neptune",
        "domain": "quantum_governance",
        "status": status,
        "lane": "LANE-135",
        "node": index,
        "minted_at": _utc_now(),
        "title": "Decoherence-to-Fuel Idempotent Fold",
        "gate": {
            "regime": "GOVERNED" if backend_receipt.get("admitted") else "HELD",
            "drift": 0.0,
            "H": 0.0,
        },
        "categories": "QHP,fold,decoherence,fuel,S*",
        "source": "cirq-qhp",
        "patent_ref": "USPTO 19/555,951",
        "metrics": metrics,
    }


def build_qhp_envelope(coin_obj: dict, metrics: dict, backend_receipt: dict) -> dict:
    cvp = cvp_compress(coin_obj)
    ceo = ceo_compress(coin_obj)
    cctp = cctp_encode(coin_obj)
    braid = [
        {"fold": k + 1, "path": "S*->decoherence->residue->fuel->Pi->S*", "hyperspace": f"H{k + 1}"}
        for k in range(int(metrics["folds"]))
    ]
    return {
        "_qhp": True,
        "_version": QHP_VERSION,
        "_protocol": PROTOCOL,
        "_echo": ECHO,
        "_no_loss": True,
        "authority": AUTHORITY,
        "name": ceo["qs1"],
        "cvp": cvp,
        "ceo": ceo,
        "cctp": cctp,
        "braid": braid,
        "runtime": metrics,
        "governed_receipt": backend_receipt,
    }


def build_qhp_svg(envelope: dict) -> str:
    raw = json.dumps(envelope, separators=(",", ":"), sort_keys=True)
    qhp = base64.b64encode(raw.encode("utf-8")).decode("ascii")
    lchc = _sha256_text("LCHC-CCTP:" + raw)[:16]
    metrics = envelope["runtime"]
    ceo = envelope["ceo"]
    cvp = envelope["cvp"]
    folds = int(metrics["folds"])
    fuel = float(metrics["fuel_density"])
    parity = float(metrics["equilibrium_even_parity_fraction"])
    horizon = "NO" if not metrics["horizon_encountered"] else "YES"
    name = html.escape(str(envelope["name"]))
    cctp_text = html.escape(str(envelope["cctp"])[:180])

    braid_lines = []
    x0, y0 = 110, 520
    width = 980
    for k in range(folds):
        x = x0 + (k / max(1, folds - 1)) * width
        y = y0 + (22 if k % 2 else -22)
        braid_lines.append(f'<line x1="{x:.1f}" y1="{y0}" x2="{x:.1f}" y2="{y}" stroke="#00e5c8" stroke-width="2" opacity="0.75"/>')
        braid_lines.append(f'<circle cx="{x:.1f}" cy="{y}" r="3" fill="#ffd700"/>')

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="700" viewBox="0 0 1200 700" id="cctp-name-card">
  <desc>CCTP-NAME:{qhp}</desc>
  <metadata>
    <name-cell xmlns:name="dcgp://name-protocol/v1">
      <name:module>QHP_DECOHERENCE_FUEL_FOLD</name:module>
      <name:author>{html.escape(AUTHORITY)}</name:author>
      <name:protocol>CCTP-QHP-v1</name:protocol>
      <name:compression>{PROTOCOL}</name:compression>
      <name:qs1>{name}</name:qs1>
      <name:lchc>{lchc}</name:lchc>
      <name:qhp encoding="base64">{qhp}</name:qhp>
    </name-cell>
  </metadata>
  <rect width="1200" height="700" rx="28" fill="#06080c"/>
  <rect x="26" y="26" width="1148" height="648" rx="22" fill="none" stroke="#1a2030" stroke-width="2"/>
  <text x="60" y="78" fill="#ffd700" font-size="28" font-family="monospace">QHP / SVG — DECOHERENCE → FUEL FOLD</text>
  <text x="60" y="112" fill="#00e5c8" font-size="15" font-family="monospace">CEO · CVP · CCTP · NAME · {folds} FOLDS · π/φ {GOV_ANGLE:.12f}</text>
  <text x="60" y="150" fill="#e8eaf0" font-size="14" font-family="monospace">{name}</text>
  <text x="60" y="190" fill="#6b7a94" font-size="13" font-family="monospace">metric g ≻ 0: {html.escape(str(metrics['metric_diagonal']))}</text>
  <text x="60" y="220" fill="#6b7a94" font-size="13" font-family="monospace">fuel density: {fuel:.6f} · S* even-parity: {parity:.6f} · horizon: {horizon}</text>
  <g transform="translate(65,270)">
    <rect x="0" y="0" width="190" height="88" rx="14" fill="#0c1018" stroke="#00e5c8"/>
    <text x="95" y="34" text-anchor="middle" fill="#e8eaf0" font-size="17" font-family="monospace">S*</text>
    <text x="95" y="60" text-anchor="middle" fill="#6b7a94" font-size="12" font-family="monospace">positive-definite</text>
    <rect x="240" y="0" width="190" height="88" rx="14" fill="#0c1018" stroke="#ffd700"/>
    <text x="335" y="34" text-anchor="middle" fill="#e8eaf0" font-size="17" font-family="monospace">DECOHERENCE</text>
    <text x="335" y="60" text-anchor="middle" fill="#6b7a94" font-size="12" font-family="monospace">syndrome / residue</text>
    <rect x="480" y="0" width="190" height="88" rx="14" fill="#0c1018" stroke="#00e5c8"/>
    <text x="575" y="34" text-anchor="middle" fill="#e8eaf0" font-size="17" font-family="monospace">FUEL</text>
    <text x="575" y="60" text-anchor="middle" fill="#6b7a94" font-size="12" font-family="monospace">feed-forward</text>
    <rect x="720" y="0" width="190" height="88" rx="14" fill="#0c1018" stroke="#ffd700"/>
    <text x="815" y="34" text-anchor="middle" fill="#e8eaf0" font-size="17" font-family="monospace">Π² = Π</text>
    <text x="815" y="60" text-anchor="middle" fill="#6b7a94" font-size="12" font-family="monospace">return to S*</text>
    <line x1="190" y1="44" x2="240" y2="44" stroke="#6b7a94" stroke-width="2"/>
    <line x1="430" y1="44" x2="480" y2="44" stroke="#6b7a94" stroke-width="2"/>
    <line x1="670" y1="44" x2="720" y2="44" stroke="#6b7a94" stroke-width="2"/>
  </g>
  <text x="60" y="455" fill="#e8eaf0" font-size="14" font-family="monospace">CCTP BRAID — residue is retained as the next fold's control input</text>
  {''.join(braid_lines)}
  <line x1="110" y1="520" x2="1090" y2="520" stroke="#334155" stroke-width="1"/>
  <text x="60" y="600" fill="#6b7a94" font-size="12" font-family="monospace">CVP: {html.escape(json.dumps(cvp, separators=(',', ':')))}</text>
  <text x="60" y="626" fill="#6b7a94" font-size="12" font-family="monospace">CEO: {html.escape(json.dumps({k: ceo[k] for k in ('_v','id','qs1','g','dr') if k in ceo}, separators=(',', ':')))}</text>
  <text x="60" y="652" fill="#4d5e7a" font-size="10" font-family="monospace">{cctp_text}</text>
</svg>'''


def fire_runtime(*, backend_url: str, coin_count: int = 3, folds: int = 22, shots: int = 128, seed_name: str = "DECOHERENCE-FUEL") -> dict:
    coin_count = max(1, min(22, int(coin_count)))
    receipts = []
    for index in range(coin_count):
        name = f"{seed_name}-{index + 1:02d}"
        metrics = run_fold_circuit(folds=folds, shots=shots, seed_name=name, seed=_stable_seed(name, index))
        frame = build_governed_frame(metrics)
        code, backend = _call_backend(backend_url, "/tick", frame)
        coin = backend.get("coin") or {}
        coin_id = str(coin.get("coin_id") or f"QHP-FUEL-{_sha256_text(name)[:16].upper()}")
        coin_obj = _coin_object(coin_id, metrics, backend, index)
        envelope = build_qhp_envelope(coin_obj, metrics, backend)
        svg = build_qhp_svg(envelope)
        receipts.append({
            "ok": code < 400 and bool(backend.get("evaluation_complete", True)),
            "backend_status": code,
            "coin_id": coin_id,
            "admitted": backend.get("admitted"),
            "status": backend.get("status"),
            "metrics": metrics,
            "cvp": envelope["cvp"],
            "ceo": envelope["ceo"],
            "cctp": envelope["cctp"],
            "qhp_svg": svg,
            "governed_receipt": backend,
        })
    return {
        "ok": all(r["ok"] for r in receipts),
        "engine": "DCGP.QHP.DECOHERENCE_FUEL_FOLD",
        "protocol": PROTOCOL,
        "qhp": QHP_VERSION,
        "authority": AUTHORITY,
        "coin_count": len(receipts),
        "folds": folds,
        "shots": shots,
        "receipts": receipts,
        "timestamp": _utc_now(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Fire the QHP decoherence-to-fuel fold runtime")
    parser.add_argument("--coins", type=int, default=3)
    parser.add_argument("--folds", type=int, default=22)
    parser.add_argument("--shots", type=int, default=128)
    parser.add_argument("--seed-name", default="DECOHERENCE-FUEL")
    parser.add_argument("--backend", default=os.environ.get("GOVERNED_BACKEND_URL", ""))
    args = parser.parse_args()
    result = fire_runtime(
        backend_url=args.backend,
        coin_count=args.coins,
        folds=args.folds,
        shots=args.shots,
        seed_name=args.seed_name,
    )
    summary = {
        "ok": result["ok"],
        "engine": result["engine"],
        "protocol": result["protocol"],
        "coin_count": result["coin_count"],
        "folds": result["folds"],
        "shots": result["shots"],
        "coins": [
            {
                "coin_id": r["coin_id"],
                "admitted": r["admitted"],
                "status": r["status"],
                "fuel_density": r["metrics"]["fuel_density"],
                "equilibrium_even_parity_fraction": r["metrics"]["equilibrium_even_parity_fraction"],
                "horizon_encountered": r["metrics"]["horizon_encountered"],
                "qs1": r["ceo"]["qs1"],
            }
            for r in result["receipts"]
        ],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
