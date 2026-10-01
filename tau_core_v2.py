#!/usr/bin/env python3
# ==========================================================================
# tau_core_v2.py — THE TAU CORE · tongue 1/3 · PYTHON (reference law)
# MODULE_ID: tau.core.v2 · BLOCK_TYPE: CORE · CONTRACT: TAU_CORE_STEP_V1
# OWNER LEDGER:
#   GOLDEN-1 · MINTED · py digest = a9a4ed1e54da45c7 · steps=64
#   ROOT CAUSE OF FUSE-1: C interleaved LCG draws; py draws sequentially.
#   E1: d_core once carried "qnorm(qc)**0 +" — deleted, filed.
#   FIX-A: params tail finite-gated. FIX-B: short read exits 2.
#   FIX-C (APPLIED): n_raw non-finite -> loud (qc, NAN, BREAK, RESET, 0).
#   ZEROS AUDIT: identity, stand-still, EPS floors, LCG mask — all honest.
#   RECOVERY: py tau_core_v2.py --selftest   (this assert is the referee)
# ==========================================================================
import math, struct

EPS = 1e-15
ACT, WATCH = 1e-12, 1e-9
MIN_COMPLETENESS = 0.5
DEFAULT_PARAMS = (0.1, 1.0, 1.0, 0.5, 0.01, 1e-8, 0.5, 0.01)
BAND_ACT, BAND_WATCH, BAND_BREAK = 0, 1, 2
ST_OK, ST_RESET, ST_NO_INFO = 0, 1, 2

def court(r):
    if r <= ACT: return BAND_ACT
    if r <= WATCH: return BAND_WATCH
    return BAND_BREAK

def qnorm(q):
    return math.sqrt(q[0]*q[0] + q[1]*q[1] + q[2]*q[2] + q[3]*q[3])

def qnormalize(q):
    n = qnorm(q)
    if n < EPS: return (1.0, 0.0, 0.0, 0.0)
    return (q[0]/n, q[1]/n, q[2]/n, q[3]/n)

def qmul(a, b):
    return (
        a[0]*b[0] - a[1]*b[1] - a[2]*b[2] - a[3]*b[3],
        a[0]*b[1] + a[1]*b[0] + a[2]*b[3] - a[3]*b[2],
        a[0]*b[2] - a[1]*b[3] + a[2]*b[0] + a[3]*b[1],
        a[0]*b[3] + a[1]*b[2] - a[2]*b[1] + a[3]*b[0],
    )

def qconj(q): return (q[0], -q[1], -q[2], -q[3])

def qrotate(q, v):
    qn = qnormalize(q)
    r = qmul(qmul(qn, (0.0, v[0], v[1], v[2])), qconj(qn))
    return (r[1], r[2], r[3])

def qsign_perm(q): return (-q[1], q[0], -q[3], q[2])

def qproject(q, v):
    d = q[0]*v[0] + q[1]*v[1] + q[2]*v[2] + q[3]*v[3]
    return (v[0]-q[0]*d, v[1]-q[1]*d, v[2]-q[2]*d, v[3]-q[3]*d)

def qclip(v, vmax):
    n = qnorm(v)
    if n > vmax:
        s = vmax / n
        return (v[0]*s, v[1]*s, v[2]*s, v[3]*s)
    return v

def _hemi(q, x):
    d = q[0]*x[0] + q[1]*x[1] + q[2]*x[2] + q[3]*x[3]
    return (-x[0], -x[1], -x[2], -x[3]) if d < 0 else x

def guarded_step(q, v, p_best, target, noise, params=DEFAULT_PARAMS):
    """one audited hop on S^3. pure. returns (q_next, residual, band, status, accepted)."""
    if not all(math.isfinite(x) for t in (q, v, p_best, target, noise) for x in t) \
       or not all(math.isfinite(x) for x in params):
        return (tuple(q), float("nan"), BAND_BREAK, ST_NO_INFO, False)
    kappa, alpha_p, alpha_g, beta, sigma, eps_c, vmax, dt = params

    qc = qnormalize(q)
    d_core = max(qc[0]*qc[0] + qc[1]*qc[1] + qc[2]*qc[2] + qc[3]*qc[3],
                 eps_c*eps_c + EPS)

    pq = qproject(qc, target)
    if qnorm(pq) < EPS:
        return (qc, float("nan"), BAND_BREAK, ST_RESET, False)

    te = _hemi(qc, target)
    pb = _hemi(qc, p_best)
    dg = (te[0]-qc[0], te[1]-qc[1], te[2]-qc[2], te[3]-qc[3])
    dp = (pb[0]-qc[0], pb[1]-qc[1], pb[2]-qc[2], pb[3]-qc[3])
    pp = qproject(qc, dp)
    gp = qproject(qc, dg)
    hp = qproject(qc, qsign_perm(qc))
    cp = qproject(qc, (dg[0]/d_core, dg[1]/d_core, dg[2]/d_core, dg[3]/d_core))
    npj = qproject(qc, noise)

    raw = tuple(kappa*hp[i] + alpha_p*pp[i] + alpha_g*gp[i] - beta*cp[i] + sigma*npj[i]
                for i in range(4))
    n_raw = qnorm(raw)
    if not math.isfinite(n_raw):
        return (qc, float("nan"), BAND_BREAK, ST_NO_INFO, False)
    sd = qnormalize(raw) if n_raw > EPS else (0.0, 0.0, 0.0, 0.0)
    qn = qnormalize((qc[0] + dt*sd[0], qc[1] + dt*sd[1], qc[2] + dt*sd[2], qc[3] + dt*sd[3]))

    r = abs(qnorm(qn) - 1.0)
    band = court(r)
    comp = max(0.0, 1.0 - r)
    status, accepted = ST_OK, band <= BAND_WATCH
    if comp < MIN_COMPLETENESS:
        status, accepted = ST_RESET, False
    return (qn, r, band, status, accepted)

def selftest(seed=12345):
    u = seed & 0x7FFFFFFF
    def nxt():
        nonlocal u
        u = (u * 1103515245 + 12345) & 0x7FFFFFFF
        return u
    def unit():
        return qnormalize(tuple((nxt() / 2147483648.0) - 1.0 for _ in range(4)))

    assert court(float("nan")) == BAND_BREAK
    assert qnormalize((0.0, 0.0, 0.0, 0.0)) == (1.0, 0.0, 0.0, 0.0)
    ni = guarded_step((1.0,0,0,0), (0,0,0,0), (0,0,0,0), (float("nan"),0,0,0), (0,0,0,0))
    assert ni[3] == ST_NO_INFO and not ni[4] and ni[0] == (1.0,0,0,0)
    rz = guarded_step((1.0,0,0,0), (0,0,0,0), (0,0,0,0), (2.0,0,0,0), (0,0,0,0))
    assert rz[3] == ST_RESET and not rz[4]

    q, v, tgt = unit(), unit(), unit()
    pb = q
    vmax = DEFAULT_PARAMS[6]
    h = 0xCBF29CE484222325
    def seal(b):
        nonlocal h
        for x in b: h = ((h ^ x) * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    best = float("inf")
    for _ in range(64):
        noise = tuple((nxt() / 2147483648.0) - 1.0 for _ in range(4))
        qn, r, band, status, ok = guarded_step(q, v, pb, tgt, noise)
        seal(struct.pack(">d", qn[0]) + struct.pack(">d", qn[1]) +
             struct.pack(">d", qn[2]) + struct.pack(">d", qn[3]) +
             struct.pack(">d", r) + bytes([band]))
        v = qclip((qn[0]-q[0], qn[1]-q[1], qn[2]-q[2], qn[3]-q[3]), vmax)
        if r < best: best, pb = r, qn
        q = qn
    return h

if __name__ == "__main__":
    import sys
    m = sys.argv[1] if len(sys.argv) > 1 else "--selftest"
    if m == "--ping":
        print("PONG")
    elif m == "--selftest":
        d = selftest()
        assert d == 0xA9A4ED1E54DA45C7, f"digest drifted: {d:016x} != a9a4ed1e54da45c7"
        print(f"TAU_CORE_SELFTEST_OK py digest={d:016x} steps=64")
    elif m == "--step":
        b = sys.stdin.buffer.read(256)
        if len(b) != 256: raise SystemExit(2)
        d = struct.unpack("<32d", b)
        qn, r, band, status, ok = guarded_step(d[0:4], d[4:8], d[8:12], d[12:16], d[16:20], d[20:28])
        out = struct.pack("<5d", *qn, r) + bytes([band, status, 1 if ok else 0])
        h = 0xCBF29CE484222325
        for x in out: h = ((h ^ x) * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
        sys.stdout.buffer.write(out + struct.pack(">Q", h))
