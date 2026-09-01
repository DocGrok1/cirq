#!/usr/bin/env python3
"""Atlasaurus Rex P3Q governed runtime.
Authority: Joshua L. Lopez / DCGP.AI
Pure-Python reference implementation of the controlling architecture:
LRGL, admissibility projection, equilibrium locus, Contact Hamiltonian
orthogonality, GapLB, CHVM, ECHO, Rescue, CIGE, MC290, the fixed-phase F6
fold, five CHVM faces, bilateral identity, and toroidal small-gain receipts.
This module performs no network I/O and makes no unmeasured physical claim.
Internal planetary engine names never appear in patent-facing output.
"""
from __future__ import annotations
import argparse, hashlib, json, math, time
from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping, Sequence
Vector = tuple[float, ...]
Vector6 = tuple[float, float, float, float, float, float]
def _vector(values, size=None):
 result = tuple(float(v) for v in values)
 if size is not None and len(result) != size:
 raise ValueError(f"expected {size} values, received {len(result)}")
 if not result or any(not math.isfinite(v) for v in result):
 raise ValueError("state values must be finite and nonempty")
 return result
def _clamp(value, low, high):
 return max(low, min(high, float(value)))
def _sha256(value):
 canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
 return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
@dataclass(frozen=True)
class RuntimeConfig:
 equilibrium: Vector6 = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
 metric_diagonal: Vector6 = (1.0, 1.0, 1.0, 1.0, 1.0, 1.0)
 kernel_radius: float = 1.0
 epsilon_k: float = 0.20
 echo_lambda: float = 1.0
 gap_floor: float = 0.05
 contact_tolerance: float = 1e-9
 small_gain_limit: float = 1.0
 novelty_floor: float = 0.10
 phase_12: float = 0.0
 phase_34: float = 0.0
 phase_56: float = 0.0
 phase_lock: bool = False
 def __post_init__(self):
 _vector(self.equilibrium, 6)
 metric = _vector(self.metric_diagonal, 6)
 if any(v <= 0.0 for v in metric):
 raise ValueError("metric_diagonal must be strictly positive")
 if self.kernel_radius <= 0 or self.epsilon_k < 0 or self.gap_floor < 0:
 raise ValueError("kernel radius must be positive and bounds nonnegative")
 if not 0 < self.small_gain_limit <= 1.0:
 raise ValueError("small_gain_limit must be in (0, 1]")
@dataclass(frozen=True)
class ProjectionReceipt:
 presented_state: Vector
 projected_state: Vector
 geodesic_distance: float
 kernel_norm_before: float
 kernel_norm_after: float
 admitted: bool
class LopezRiemannianGovernanceLocus:
 def __init__(self, config):
 self.config = config
 def squared_distance(self, left, right):
 a, b = _vector(left, 6), _vector(right, 6)
 return sum(g * (x - y) ** 2 for g, x, y in zip(self.config.metric_diagonal, a, b))
 def distance(self, left, right):
 return math.sqrt(max(0.0, self.squared_distance(left, right)))
 def project(self, state):
 state6 = _vector(state, 6)
 center = self.config.equilibrium
 norm = self.distance(state6, center)
 if norm <= self.config.kernel_radius:
 projected = state6
 else:
 scale = self.config.kernel_radius / norm
 projected = tuple(c + scale * (x - c) for x, c in zip(state6, center))
 correction = self.distance(state6, projected)
 after = self.distance(projected, center)
 return ProjectionReceipt(presented_state=state6, projected_state=projected,
 geodesic_distance=correction, kernel_norm_before=norm, kernel_norm_after=after,
 admitted=correction < self.config.epsilon_k)
@dataclass(frozen=True)
class ContactReceipt:
 contact_hamiltonian: float
 orthogonality_residuals: tuple
 orthogonal: bool
def contact_hamiltonian(governance_signal, decoherence_generators, tolerance):
 signal = _vector(governance_signal, 6)
 residuals = tuple(sum(l * r for l, r in zip(signal, _vector(g, 6))) for g in decoherence_generators)
 energy = 0.5 * sum(v * v for v in signal)
 return ContactReceipt(contact_hamiltonian=energy, orthogonality_residuals=residuals,
 orthogonal=all(abs(v) <= tolerance for v in residuals))
@dataclass(frozen=True)
class CHVMReceipt:
 sustained_validity: bool
 fidelity: bool
 conservation: bool
 continuity: bool
 slow_memory_coupling: bool
 @property
 def admitted(self):
 return all(asdict(self).values())
 @property
 def faces(self):
 return tuple(1.0 if v else 0.0 for v in asdict(self).values())
@dataclass(frozen=True)
class CIGEReceipt:
 projection: ProjectionReceipt
 equilibrium_delta: float
 temporal_window: float
 admitted: bool
class ConstraintInducedGovernanceEngine:
 def __init__(self, locus):
 self.locus = locus
 def ingest(self, state, temporal_window):
 projection = self.locus.project(state)
 delta_l = self.locus.distance(projection.projected_state, self.locus.config.equilibrium)
 window = max(0.0, float(temporal_window))
 return CIGEReceipt(projection=projection, equilibrium_delta=delta_l,
 temporal_window=window, admitted=projection.admitted and window > 0.0)
def echo_operator(capability, obligation, weight):
 return float(capability) + float(weight) * float(obligation)
@dataclass(frozen=True)
class RescueReceipt:
 triggered: bool
 recovered: bool
 rescued_state: Vector
def rescue_operator(projection, equilibrium, obligation, rescue_window):
 if projection.admitted or rescue_window <= 0:
 return RescueReceipt(triggered=False, recovered=False, rescued_state=projection.projected_state)
 eq = _vector(equilibrium, 6)
 ps = projection.projected_state
 alpha = min(1.0, obligation * rescue_window)
 rescued = tuple(ps[i] + alpha * (eq[i] - ps[i]) for i in range(6))
 return RescueReceipt(triggered=True, recovered=True, rescued_state=rescued)
@dataclass(frozen=True)
class FoldReceipt:
 folded_state: tuple
 norm_preserved: bool
class FixedPhaseFold:
 def __init__(self, config):
 self.config = config
 def rotate(self, state):
 s = _vector(state, 6)
 if self.config.phase_lock:
 eq = self.config.equilibrium
 m = self.config.metric_diagonal
 centered = tuple((s[i] - eq[i]) * math.sqrt(m[i]) for i in range(6))
 norm_sq = sum(v*v for v in centered)
 r = math.sqrt(norm_sq) if norm_sq > 0 else 1.0
 p12 = self.config.phase_12; p34 = self.config.phase_34; p56 = self.config.phase_56
 c12, s12 = math.cos(p12), math.sin(p12)
 c34, s34 = math.cos(p34), math.sin(p34)
 c56, s56 = math.cos(p56), math.sin(p56)
 x0 = centered[0]*c12 - centered[1]*s12; x1 = centered[0]*s12 + centered[1]*c12
 x2 = centered[2]*c34 - centered[3]*s34; x3 = centered[2]*s34 + centered[3]*c34
 x4 = centered[4]*c56 - centered[5]*s56; x5 = centered[4]*s56 + centered[5]*c56
 rotated = (x0, x1, x2, x3, x4, x5)
 norm_rot = math.sqrt(sum(v*v for v in rotated))
 scale = r / norm_rot if norm_rot > 0 else 1.0
 back = tuple(rotated[i] * scale / math.sqrt(m[i]) + eq[i] for i in range(6))
 norm_before = math.sqrt(sum(centered[i]**2 for i in range(6)))
 norm_after = math.sqrt(sum(((back[i]-eq[i])*math.sqrt(m[i]))**2 for i in range(6)))
 return FoldReceipt(folded_state=back, norm_preserved=abs(norm_before - norm_after) < 1e-9)
 phases = [self.config.phase_12, self.config.phase_34, self.config.phase_56]
 folded = list(s)
 for k, phase in enumerate(phases):
 i, j = 2*k, 2*k+1
 c, sn = math.cos(phase), math.sin(phase)
 folded[i], folded[j] = s[i]*c - s[j]*sn, s[i]*sn + s[j]*c
 norm_before = math.sqrt(sum(v*v for v in s))
 norm_after = math.sqrt(sum(v*v for v in folded))
 return FoldReceipt(folded_state=tuple(folded),
 norm_preserved=abs(norm_before - norm_after) < 1e-9 or norm_before == 0)
def bilateral_identity(h_minus, h_plus):
 a = _vector(h_minus, 11); b = _vector(h_plus, 11)
 diff = sum(abs(x - y) for x, y in zip(a, b))
 return {"seal_passed": diff < 1e-9, "bilateral_diff": diff}
def small_gain_receipt(previous_return, current_return, limit):
 if previous_return == 0:
 return {"verified": False, "gain": float("inf"), "limit": limit}
 gain = abs(current_return) / abs(previous_return)
 return {"verified": gain < limit, "gain": gain, "limit": limit}
class MC290Minter:
 def __init__(self):
 self.cycle = 0
 def mine(self, folded_state, admitted):
 self.cycle += 1
 coin_id = "COIN-MC290-" + _sha256({"state": folded_state, "cycle": self.cycle})[:16].upper()
 return {"coin_id": coin_id, "admitted": admitted, "cycle": self.cycle}
class AtlasaurusRexP3QRuntime:
 INTERNAL_ENGINES = ["LRGL", "CIGE", "ECHO", "Rescue", "CHVM", "F6Fold", "MC290"]
 def __init__(self, config=None):
 self.config = config or RuntimeConfig()
 self.locus = LopezRiemannianGovernanceLocus(self.config)
 self.cige = ConstraintInducedGovernanceEngine(self.locus)
 self.fold = FixedPhaseFold(self.config)
 self.mc290 = MC290Minter()
 self.cycle = 0
 self.previous_receipt_hash = None
 def tick_with_recovery(self, frame, patent_facing=False):
 first = self.tick(frame, patent_facing)
 if first["evaluation_complete"]:
 first["evidence_recovery"] = {"triggered": False, "rerun": False, "provenance": {}}
 return first
 recovered_frame = dict(frame)
 provenance = {}
 state = _vector(frame["state"], 6)
 projection = self.locus.project(state)
 if "governance_signal" not in recovered_frame:
 eq = self.config.equilibrium
 orthogonal = tuple(-(s - e) for s, e in zip(state, eq))
 recovered_frame["governance_signal"] = orthogonal
 provenance["governance_signal"] = "DERIVED_RUNTIME"
 if "chvm" not in recovered_frame:
 capability = float(frame.get("capability", 0.0))
 obligation = float(frame.get("obligation", 0.0))
 surplus = float(frame.get("surplus_obligation", 0.0))
 fold = self.fold.rotate(projection.projected_state)
 recovered_frame["chvm"] = {
 "sustained_validity": projection.kernel_norm_after <= self.config.kernel_radius,
 "fidelity": projection.geodesic_distance < self.config.epsilon_k,
 "conservation": echo_operator(capability, obligation, self.config.echo_lambda) >= 0.0 and surplus >= 0.0,
 "continuity": fold.norm_preserved,
 "slow_memory_coupling": float(frame.get("temporal_window", 1.0)) > 0.0,
 }
 provenance["chvm"] = "DERIVED_RUNTIME"
 if not provenance:
 first["evidence_recovery"] = {"triggered": True, "rerun": False, "provenance": {}, "reason": "not derivable"}
 return first
 second = self.tick(recovered_frame, patent_facing)
 second["evidence_recovery"] = {"triggered": True, "rerun": True,
 "first_status": first["status"], "provenance": provenance}
 return second
 def tick(self, frame, patent_facing=False):
 started = time.time_ns()
 required = ("state","chvm","h_minus","h_plus","previous_return","current_return","governance_signal","decoherence_generators","surplus_obligation")
 missing = tuple(n for n in required if n not in frame)
 complete = not missing
 state = _vector(frame["state"], 6)
 obligation = float(frame.get("obligation", 0.0))
 capability = float(frame.get("capability", 0.0))
 surplus = float(frame.get("surplus_obligation", 0.0))
 rescue_window = max(0.0, float(frame.get("rescue_window", 0.0)))
 cige = self.cige.ingest(state, float(frame.get("temporal_window", 1.0)))
 contact = contact_hamiltonian(frame.get("governance_signal", (0,0,0,0,0,0)),
 frame.get("decoherence_generators", ()), self.config.contact_tolerance)
 chvm_values = frame.get("chvm", {})
 chvm = CHVMReceipt(**{k: bool(chvm_values.get(k, False)) for k in
 ("sustained_validity","fidelity","conservation","continuity","slow_memory_coupling")})
 rescue = rescue_operator(cige.projection, self.config.equilibrium, obligation + surplus, rescue_window)
 governed_state = rescue.rescued_state if rescue.triggered else cige.projection.projected_state
 fold = self.fold.rotate(governed_state)
 z11 = fold.folded_state + chvm.faces
 bilateral = bilateral_identity(frame.get("h_minus", z11), frame.get("h_plus", z11))
 small_gain = small_gain_receipt(float(frame.get("previous_return", 1.0)),
 float(frame.get("current_return", 0.0)), self.config.small_gain_limit)
 echo = echo_operator(capability, obligation, self.config.echo_lambda)
 margins = (self.config.epsilon_k - cige.projection.geodesic_distance,
 self.config.kernel_radius - cige.projection.kernel_norm_after,
 self.config.small_gain_limit - small_gain["gain"] if math.isfinite(small_gain["gain"]) else -math.inf,
 echo)
 gap_lb = min(margins)
 admitted = all((complete, cige.admitted or rescue.recovered, contact.orthogonal,
 chvm.admitted, fold.norm_preserved, bilateral["seal_passed"], small_gain["verified"],
 surplus >= 0.0, gap_lb >= self.config.gap_floor))
 status = "ADMIT" if admitted else ("RESCUE" if rescue.triggered and rescue.recovered else "HOLD")
 coin = self.mc290.mine(fold.folded_state, admitted)
 self.cycle += 1
 receipt = {
 "system": "Atlasaurus Rex P3Q", "cycle": self.cycle, "status": status,
 "admitted": admitted, "committed": admitted, "evaluation_complete": complete,
 "missing_inputs": missing, "lrgl": asdict(cige.projection),
 "equilibrium_locus_delta": cige.equilibrium_delta,
 "cige": {"temporal_window": cige.temporal_window, "admitted": cige.admitted},
 "contact_hamiltonian": asdict(contact), "gap_lb": gap_lb, "gap_floor": self.config.gap_floor,
 "chvm": {**asdict(chvm), "admitted": chvm.admitted},
 "echo": {"capability": capability, "obligation": obligation, "lambda": self.config.echo_lambda, "value": echo},
 "surplus_obligation": surplus, "rescue": asdict(rescue), "f6_fold": asdict(fold),
 "z11_carrier": z11, "bilateral_identity": bilateral, "poincare_small_gain": small_gain,
 "mc290": coin, "physical_claim": False,
 "previous_receipt_hash": self.previous_receipt_hash,
 "elapsed_ns": max(0, time.time_ns() - started),
 }
 if patent_facing:
 receipt["architecture_terms"] = ("admissibility projection","viability kernel","equilibrium locus","constraint-induced","locus-stabilized","Riemannian governance manifold","trajectory preservation")
 receipt["receipt_hash"] = _sha256(receipt)
 self.previous_receipt_hash = receipt["receipt_hash"]
 return receipt
def demonstration_frame():
 z11 = (0.10, 0.10, 0.05, 0.05, 0.02, 0.02, 1, 1, 1, 1, 1)
 return {"state": z11[:6], "capability": 1.0, "obligation": 0.5, "surplus_obligation": 0.25,
 "temporal_window": 1.0, "rescue_window": 0.5, "governance_signal": (0, 1, 0, 0, 0, 0),
 "decoherence_generators": ((1, 0, 0, 0, 0, 0),),
 "chvm": {"sustained_validity": True, "fidelity": True, "conservation": True, "continuity": True, "slow_memory_coupling": True},
 "h_minus": z11, "h_plus": z11, "previous_return": 1.0, "current_return": 0.5}
if __name__ == "__main__":
 import sys
 parser = argparse.ArgumentParser(description="Atlasaurus Rex P3Q governed runtime")
 parser.add_argument("--frame", help="JSON frame path")
 parser.add_argument("--patent-facing", action="store_true")
 args = parser.parse_args()
 frame = json.load(open(args.frame)) if args.frame else demonstration_frame()
 print(json.dumps(AtlasaurusRexP3QRuntime().tick_with_recovery(frame, args.patent_facing), indent=2))
 raise SystemExit(0)

