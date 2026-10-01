// ==========================================================================
// tau_core.rs — THE TAU CORE · tongue 3/3 · RUST (the safe one)
// MODULE_ID: tau.core.v2 · BLOCK_TYPE: CORE · CONTRACT: TAU_CORE_STEP_V1
// build: rustc -O tau_core.rs -o tau_core_rs.exe
// GOLDEN-1: selftest must print digest=a9a4ed1e54da45c7 (py is the law).
// DRAW ORDER: sequential — q(4), v(4), tgt(4), then 4 noise/step.
// FIX-A: params tail gated. FIX-B: --step short read exits 2.
// FIX-C (APPLIED): n_raw non-finite -> loud (qc, NAN, BREAK, RESET, false).
// ==========================================================================
use std::io::{Read, Write};
use std::convert::TryInto;
use std::process;

const EPS: f64 = 1e-15;
const ACT: f64 = 1e-12;
const WATCH: f64 = 1e-9;
const MINCOMP: f64 = 0.5;
const GOLDEN: u64 = 0xA9A4ED1E54DA45C7;
const DEF_P: [f64; 8] = [0.1, 1.0, 1.0, 0.5, 0.01, 1e-8, 0.5, 0.01];

fn qnorm(q: &[f64; 4]) -> f64 { (q[0]*q[0] + q[1]*q[1] + q[2]*q[2] + q[3]*q[3]).sqrt() }
fn qdot(a: &[f64; 4], b: &[f64; 4]) -> f64 { a[0]*b[0] + a[1]*b[1] + a[2]*b[2] + a[3]*b[3] }

fn qnormalize(q: &[f64; 4]) -> [f64; 4] {
    let n = qnorm(q);
    if n < EPS { return [1.0, 0.0, 0.0, 0.0]; }
    [q[0]/n, q[1]/n, q[2]/n, q[3]/n]
}
fn qproject(q: &[f64; 4], v: &[f64; 4]) -> [f64; 4] {
    let d = qdot(q, v);
    [v[0]-q[0]*d, v[1]-q[1]*d, v[2]-q[2]*d, v[3]-q[3]*d]
}
fn qclip(v: &[f64; 4], vmax: f64) -> [f64; 4] {
    let n = qnorm(v);
    if n > vmax { let s = vmax/n; [v[0]*s, v[1]*s, v[2]*s, v[3]*s] } else { *v }
}
fn qsign_perm(q: &[f64; 4]) -> [f64; 4] { [-q[1], q[0], -q[3], q[2]] }
fn hemi(q: &[f64; 4], x: &[f64; 4]) -> [f64; 4] {
    if qdot(q, x) < 0.0 { [-x[0], -x[1], -x[2], -x[3]] } else { *x }
}
fn court(r: f64) -> u8 {
    if r <= ACT { 0 } else if r <= WATCH { 1 } else { 2 }
}

fn guarded_step(q: &[f64; 4], v: &[f64; 4], pb: &[f64; 4], tg: &[f64; 4],
                nz: &[f64; 4], p: &[f64; 8]) -> ([f64; 4], f64, u8, u8, bool) {
    if ![q, v, pb, tg, nz].iter().all(|t| t.iter().all(|x| x.is_finite()))
       || !p.iter().all(|x| x.is_finite()) {
        return (*q, f64::NAN, 2, 2, false);
    }
    let (kappa, alpha_p, alpha_g, beta, sigma, eps_c, _vmax, dt) =
        (p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7]);

    let qc = qnormalize(q);
    let d_core = qdot(&qc, &qc).max(eps_c*eps_c + EPS);
    let pq = qproject(&qc, tg);
    if qnorm(&pq) < EPS {
        return (qc, f64::NAN, 2, 1, false);
    }
    let te = hemi(&qc, tg);
    let pbe = hemi(&qc, pb);
    let dg = [te[0]-qc[0], te[1]-qc[1], te[2]-qc[2], te[3]-qc[3]];
    let dp = [pbe[0]-qc[0], pbe[1]-qc[1], pbe[2]-qc[2], pbe[3]-qc[3]];
    let pp = qproject(&qc, &dp);
    let gp = qproject(&qc, &dg);
    let hp = qproject(&qc, &qsign_perm(&qc));
    let ct = [dg[0]/d_core, dg[1]/d_core, dg[2]/d_core, dg[3]/d_core];
    let cp = qproject(&qc, &ct);
    let npj = qproject(&qc, nz);

    let mut raw = [0.0f64; 4];
    for i in 0..4 {
        raw[i] = kappa*hp[i] + alpha_p*pp[i] + alpha_g*gp[i] - beta*cp[i] + sigma*npj[i];
    }

    let n_raw = qnorm(&raw);
    if !n_raw.is_finite() {
        return (qc, f64::NAN, 2, 1, false);
    }
    let sd = if n_raw > EPS { qnormalize(&raw) } else { [0.0, 0.0, 0.0, 0.0] };

    let qr = [qc[0] + dt*sd[0], qc[1] + dt*sd[1], qc[2] + dt*sd[2], qc[3] + dt*sd[3]];
    let qn = qnormalize(&qr);
    let r = (qnorm(&qn) - 1.0).abs();
    let band = court(r);
    let comp = (1.0 - r).max(0.0);
    let mut status: u8 = 0;
    let mut accepted = band <= 1;
    if comp < MINCOMP { status = 1; accepted = false; }
    (qn, r, band, status, accepted)
}

fn seal_bytes(h: &mut u64, bytes: &[u8]) {
    for &b in bytes { *h ^= b as u64; *h = h.wrapping_mul(0x100000001B3); }
}
fn seal_d(h: &mut u64, x: f64) { seal_bytes(h, &x.to_bits().to_be_bytes()); }

struct Lcg(u32);
impl Lcg {
    fn nxt(&mut self) -> u32 {
        self.0 = self.0.wrapping_mul(1103515245).wrapping_add(12345) & 0x7FFF_FFFF;
        self.0
    }
    fn draw(&mut self) -> f64 { (self.nxt() as f64) / 2147483648.0 - 1.0 }
}

fn selftest() -> u64 {
    assert_eq!(court(f64::NAN), 2);
    assert_eq!(qnormalize(&[0.0, 0.0, 0.0, 0.0]), [1.0, 0.0, 0.0, 0.0]);
    let (qn, _r, _b, st, ok) = guarded_step(
        &[1.0, 0.0, 0.0, 0.0], &[0.0; 4], &[0.0; 4], &[f64::NAN, 0.0, 0.0, 0.0], &[0.0; 4], &DEF_P);
    assert_eq!(st, 2); assert!(!ok); assert_eq!(qn, [1.0, 0.0, 0.0, 0.0]);
    let (_qn, _r, _b, st, ok) = guarded_step(
        &[1.0, 0.0, 0.0, 0.0], &[0.0; 4], &[0.0; 4], &[2.0, 0.0, 0.0, 0.0], &[0.0; 4], &DEF_P);
    assert_eq!(st, 1); assert!(!ok);

    let mut rng = Lcg(12345);
    let mut q  = qnormalize(&[rng.draw(), rng.draw(), rng.draw(), rng.draw()]);
    let mut v  = qnormalize(&[rng.draw(), rng.draw(), rng.draw(), rng.draw()]);
    let tgt = qnormalize(&[rng.draw(), rng.draw(), rng.draw(), rng.draw()]);
    let mut pb = q;
    let vmax = DEF_P[6];
    let mut h: u64 = 0xCBF29CE484222325;
    let mut best = f64::INFINITY;
    for _ in 0..64 {
        let noise = [rng.draw(), rng.draw(), rng.draw(), rng.draw()];
        let (qn, r, band, _st, _ok) = guarded_step(&q, &v, &pb, &tgt, &noise, &DEF_P);
        seal_d(&mut h, qn[0]); seal_d(&mut h, qn[1]);
        seal_d(&mut h, qn[2]); seal_d(&mut h, qn[3]);
        seal_d(&mut h, r);
        seal_bytes(&mut h, &[band]);
        let dv = [qn[0]-q[0], qn[1]-q[1], qn[2]-q[2], qn[3]-q[3]];
        v = qclip(&dv, vmax);
        if r < best { best = r; pb = qn; }
        q = qn;
    }
    h
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let m = args.get(1).map(|s| s.as_str()).unwrap_or("--selftest");
    match m {
        "--ping" => { println!("PONG"); }
        "--selftest" => {
            let d = selftest();
            if d != GOLDEN {
                eprintln!("DIGEST_DRIFT rs got={:016x} want=a9a4ed1e54da45c7", d);
                process::exit(1);
            }
            println!("TAU_CORE_SELFTEST_OK rs digest={:016x} steps=64", d);
        }
        "--step" => {
            let mut buf = [0u8; 256];
            if std::io::stdin().read_exact(&mut buf).is_err() { process::exit(2); }
            let mut inn = [0.0f64; 32];
            for i in 0..32 {
                inn[i] = f64::from_le_bytes(buf[i*8..i*8+8].try_into().unwrap());
            }
            let q4: [f64; 4] = inn[0..4].try_into().unwrap();
            let v4: [f64; 4] = inn[4..8].try_into().unwrap();
            let p4: [f64; 4] = inn[8..12].try_into().unwrap();
            let t4: [f64; 4] = inn[12..16].try_into().unwrap();
            let n4: [f64; 4] = inn[16..20].try_into().unwrap();
            let pa: [f64; 8] = inn[20..28].try_into().unwrap();
            let (qn, r, band, status, ok) = guarded_step(&q4, &v4, &p4, &t4, &n4, &pa);
            let mut out: Vec<u8> = Vec::with_capacity(51);
            for x in qn.iter() { out.extend_from_slice(&x.to_le_bytes()); }
            out.extend_from_slice(&r.to_le_bytes());
            out.push(band); out.push(status); out.push(if ok { 1 } else { 0 });
            let mut h: u64 = 0xCBF29CE484222325;
            seal_bytes(&mut h, &out);
            out.extend_from_slice(&h.to_be_bytes());
            std::io::stdout().write_all(&out).unwrap();
        }
        _ => { eprintln!("unknown mode"); process::exit(2); }
    }
}
