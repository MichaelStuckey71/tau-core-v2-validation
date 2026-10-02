#!/usr/bin/env python3
# ==========================================================================
# tau_golden.py — THE GOLDEN TEST · one command, four gates
# MODULE_ID: tau.golden.v1 · BLOCK_TYPE: REFEREE · CONTRACT: TAU_CORE_STEP_V1
# ADDENDUM LAW: judges the triad, never edits it. additive only.
#   LAYER 1 (NaN router) lives inside the cores' math — no off-switch.
#   LAYER 2 (optocoupler) = gates 2+3 here — corrupt light is dropped,
#   bad news arrives sealed. jumper closed by default.
# GATE 1 DIGEST  — every tongue's selftest prints the golden number
# GATE 2 WIRE    — probe+edge frames byte-identical across tongues, sealed
# GATE 3 COUPLER — corrupt seal detected; NaN routed loud, unchanged, sealed
# GATE 4 TOOLS   — benchmark registry; absent tool = honest SKIP, not pass
# E3 (filed): earlier bus demo packed 28 doubles into 32 slots. fixed.
# ==========================================================================
import math, os, struct, subprocess, sys

GOLDEN    = 0xA9A4ED1E54DA45C7
FNV_OFF   = 0xCBF29CE484222325
FNV_PRIME = 0x100000001B3
DEFAULT_P = (0.1, 1.0, 1.0, 0.5, 0.01, 1e-8, 0.5, 0.01)
HERE      = os.path.dirname(os.path.abspath(__file__))

TONGUES = {
    "py": [sys.executable, os.path.join(HERE, "tau_core_v2.py")],
    "c":  [os.path.join(HERE, "tau_core_c.exe")],
    "rs": [os.path.join(HERE, "tau_core_rs.exe")],
}
BUILD_HINTS = {
    "c":  "gcc -std=c11 -O2 -ffp-contract=off tau_core.c -o tau_core_c.exe -lm",
    "rs": "rustc -O tau_core.rs -o tau_core_rs.exe",
}
TOOLS = {  # additive registry: name -> (filename, success marker)
    "tracer": ("tau_tracer_rigorous_v2.py", "ALL_RIGOROUS_TRACER_OK"),
}

def fnv(data):
    h = FNV_OFF
    for b in data:
        h = ((h ^ b) * FNV_PRIME) & 0xFFFFFFFFFFFFFFFF
    return h

def seal_ok(frame):
    return len(frame) == 51 and fnv(frame[:43]) == struct.unpack(">Q", frame[43:51])[0]

def run(cmd, inp=None, timeout=60):
    return subprocess.run(cmd, input=inp, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, timeout=timeout)

def exists(t):
    return os.path.exists(TONGUES[t][1] if t == "py" else TONGUES[t][0])

def frame(q, v, pb, tg, nz, P=DEFAULT_P, pad=(0.0, 0.0, 0.0, 0.0)):
    # 5 vectors (20 doubles) + 8 params + 4 pad = 32 doubles = 256 bytes. E3.
    return struct.pack("<32d", *q, *v, *pb, *tg, *nz, *P, *pad)

PROBES = {
    "healthy": frame((0.9, 0.1, 0.2, 0.3), (0, 0, 0, 0), (0.9, 0.1, 0.2, 0.3),
                     (0.5, 0.5, 0.5, 0.5), (0.1, -0.1, 0.05, -0.05)),
    "nan_tgt": frame((0.9, 0.1, 0.2, 0.3), (0, 0, 0, 0), (0, 0, 0, 0),
                     (float("nan"), 0, 0, 0), (0, 0, 0, 0)),
    "ghost":   frame((0.9, 0.1, 0.2, 0.3), (0, 0, 0, 0), (0, 0, 0, 0),
                     (0, 0, 0, 0), (0, 0, 0, 0)),
    "zero_q":  frame((0, 0, 0, 0), (0, 0, 0, 0), (0, 0, 0, 0),
                     (0.5, 0.5, 0.5, 0.5), (0, 0, 0, 0)),
}

def gate1():
    notes, fails = [], []
    for t in TONGUES:
        if not exists(t):
            notes.append(f"{t}=SKIP(build:{BUILD_HINTS[t]})" if t in BUILD_HINTS
                         else f"{t}=SKIP(no file)")
            continue
        try:
            p = run(TONGUES[t] + ["--selftest"])
            out = p.stdout.decode(errors="replace").strip()
            if "SELFTEST_OK" in out and f"{GOLDEN:016x}" in out:
                notes.append(f"{t}=PASS")
            else:
                err = (out or p.stderr.decode(errors="replace").strip()
                       or f"exit={p.returncode}")
                fails.append(f"{t}=FAIL({err[:120]})")
        except Exception as e:
            fails.append(f"{t}=FAIL({type(e).__name__})")
    return notes, fails

def gate2():
    notes, fails = [], []
    have = [t for t in TONGUES if exists(t)]
    if len(have) < 2:
        return ["SKIP(need >=2 built tongues)"], []
    for name, fr in PROBES.items():
        outs = {}
        for t in have:
            try:
                p = run(TONGUES[t] + ["--step"], fr)
            except Exception as e:
                fails.append(f"{name}/{t}=FAIL({type(e).__name__})"); continue
            if p.returncode != 0 or len(p.stdout) != 51:
                fails.append(f"{name}/{t}=FAIL(rc={p.returncode},len={len(p.stdout)})")
            else:
                outs[t] = p.stdout
        if not outs:
            continue
        ref_t = "py" if "py" in outs else sorted(outs)[0]
        ref = outs[ref_t]
        for t, o in outs.items():
            if not seal_ok(o):
                fails.append(f"{name}/{t}=FAIL(seal)")
            elif o != ref:
                fails.append(f"{name}/{t}=FAIL(wire!={ref_t})")
        if not any(f.startswith(name + "/") for f in fails):
            notes.append(f"{name}=PASS({len(outs)} tongues, sealed, identical)")
    return notes, fails

def gate3():
    notes, fails = [], []
    bad = bytearray(PROBES["healthy"]); bad[7] ^= 0x01
    notes.append("tamper=DROPPABLE" if not seal_ok(bytes(bad))
                 else "tamper=FAIL(seal survived corruption)")
    live = [t for t in ("py", "c", "rs") if exists(t)]
    if not live:
        notes.append("nan_route=SKIP(no tongues)")
        return notes, fails
    t = live[0]
    p = run(TONGUES[t] + ["--step"], PROBES["nan_tgt"])
    o = p.stdout
    if len(o) == 51 and seal_ok(o):
        qback = struct.unpack("<4d", o[:32])
        r = struct.unpack("<d", o[32:40])[0]
        status, ok = o[41], o[42]
        if qback == struct.unpack("<4d", PROBES["nan_tgt"][:32]) \
           and math.isnan(r) and status == 2 and not ok:
            notes.append(f"nan_route/{t}=PASS(unchanged,loud,sealed)")
        else:
            fails.append(f"nan_route/{t}=FAIL(st={status},ok={ok})")
    else:
        fails.append(f"nan_route/{t}=FAIL(no sealed frame)")
    return notes, fails

def gate4():
    notes, fails = [], []
    for name, (fname, marker) in TOOLS.items():
        path = os.path.join(HERE, fname)
        if not os.path.exists(path):
            notes.append(f"{name}=SKIP({fname} not on disk - honest skip, not a pass)")
            continue
        try:
            p = run([sys.executable, path], timeout=300)
            out = (p.stdout + p.stderr).decode(errors="replace")
            if marker in out:
                notes.append(f"{name}=PASS")
            else:
                fails.append(f"{name}=FAIL({out.strip()[-150:]})")
        except Exception as e:
            fails.append(f"{name}=FAIL({type(e).__name__})")
    return notes, fails

def main():
    g1n, g1f = gate1(); g2n, g2f = gate2(); g3n, g3f = gate3(); g4n, g4f = gate4()
    print("TAU_GOLDEN gate1 digest :", " ".join(g1n + g1f) or "none")
    print("TAU_GOLDEN gate2 wire   :", " ".join(g2n + g2f) or "none")
    print("TAU_GOLDEN gate3 coupler:", " ".join(g3n + g3f) or "none")
    print("TAU_GOLDEN gate4 tools  :", " ".join(g4n + g4f) or "none")
    fails = g1f + g2f + g3f + g4f
    npass = len(g1n + g2n + g3n + g4n)
    if fails:
        print(f"TAU_GOLDEN_VERDICT: NOT_GOLDEN ({npass} pass, {len(fails)} fail) "
              f"- py is the law, paste this output back")
        return 1
    print(f"TAU_GOLDEN_VERDICT: ALL_GOLDEN_OK ({npass} pass, 0 fail)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
