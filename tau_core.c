/* ==========================================================================
   tau_core.c — THE TAU CORE · tongue 2/3 · C (the fast one)
   MODULE_ID: tau.core.v2 · BLOCK_TYPE: CORE · CONTRACT: TAU_CORE_STEP_V1
   BUILD LAW (no fastmath, ever — fma contraction kills agreement):
     gcc -std=c11 -O2 -ffp-contract=off tau_core.c -o tau_core_c.exe -lm
   GOLDEN-1: selftest must print digest=a9a4ed1e54da45c7 (py is the law).
   DRAW ORDER: SEQUENTIAL — q(4), v(4), tgt(4), then 4 noise/step.
   FIX-A: params tail gated. FIX-B: --step short read exits 2.
   FIX-C (APPLIED): n_raw non-finite -> loud (qc, NAN, BREAK, RESET, 0).
   ========================================================================== */
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <math.h>

#define EPS 1e-15
#define ACT 1e-12
#define WATCH 1e-9
#define MINCOMP 0.5
#define GOLDEN 0xA9A4ED1E54DA45C7ull

enum { BAND_ACT=0, BAND_WATCH=1, BAND_BREAK=2 };
enum { ST_OK=0, ST_RESET=1, ST_NO_INFO=2 };

static const double DEF_P[8] = {0.1, 1.0, 1.0, 0.5, 0.01, 1e-8, 0.5, 0.01};

static double qnorm(const double q[4]){
    return sqrt(q[0]*q[0] + q[1]*q[1] + q[2]*q[2] + q[3]*q[3]);
}
static double qdot(const double a[4], const double b[4]){
    return a[0]*b[0] + a[1]*b[1] + a[2]*b[2] + a[3]*b[3];
}
static void qnormalize(const double q[4], double o[4]){
    double n = qnorm(q);
    if (n < EPS){ o[0]=1.0; o[1]=0.0; o[2]=0.0; o[3]=0.0; return; }
    o[0]=q[0]/n; o[1]=q[1]/n; o[2]=q[2]/n; o[3]=q[3]/n;
}
static void qproject(const double q[4], const double v[4], double o[4]){
    double d = qdot(q, v);
    o[0]=v[0]-q[0]*d; o[1]=v[1]-q[1]*d; o[2]=v[2]-q[2]*d; o[3]=v[3]-q[3]*d;
}
static void qclip(const double v[4], double vmax, double o[4]){
    double n = qnorm(v);
    if (n > vmax){ double s = vmax/n; o[0]=v[0]*s; o[1]=v[1]*s; o[2]=v[2]*s; o[3]=v[3]*s; }
    else memcpy(o, v, sizeof(double)*4);
}
static void qsign_perm(const double q[4], double o[4]){
    o[0]=-q[1]; o[1]=q[0]; o[2]=-q[3]; o[3]=q[2];
}
static void hemi(const double q[4], const double x[4], double o[4]){
    if (qdot(q, x) < 0.0){ o[0]=-x[0]; o[1]=-x[1]; o[2]=-x[2]; o[3]=-x[3]; }
    else memcpy(o, x, sizeof(double)*4);
}
static int court(double r){
    if (r <= ACT) return BAND_ACT;
    if (r <= WATCH) return BAND_WATCH;
    return BAND_BREAK;
}

static uint64_t FNV = 0xCBF29CE484222325ULL;
static void seal(uint8_t b){ FNV ^= b; FNV *= 0x100000001B3ULL; }
static void seal_d(double x){
    uint64_t u; memcpy(&u, &x, 8);
    for (int i = 7; i >= 0; i--) seal((uint8_t)(u >> (8*i)));
}
static uint32_t lcg(uint32_t *u){ *u = (*u * 1103515245u + 12345u) & 0x7FFFFFFFu; return *u; }
static double draw(uint32_t *u){ return (double)lcg(u) / 2147483648.0 - 1.0; }

static int guarded_step(const double q[4], const double v[4], const double pb[4],
                        const double tg[4], const double nz[4], const double P[8],
                        double q_next[4], double *res, int *band, int *ok)
{
    for (int i = 0; i < 4; i++){
        if (!isfinite(q[i]) || !isfinite(v[i]) || !isfinite(pb[i]) ||
            !isfinite(tg[i]) || !isfinite(nz[i])){
            memcpy(q_next, q, sizeof(double)*4);
            *res = NAN; *band = BAND_BREAK; *ok = 0; return ST_NO_INFO;
        }
    }
    for (int i = 0; i < 8; i++){
        if (!isfinite(P[i])){
            memcpy(q_next, q, sizeof(double)*4);
            *res = NAN; *band = BAND_BREAK; *ok = 0; return ST_NO_INFO;
        }
    }

    double qc[4]; qnormalize(q, qc);
    double d_core = fmax(qdot(qc, qc), P[5]*P[5] + EPS);

    double pq[4]; qproject(qc, tg, pq);
    if (qnorm(pq) < EPS){
        memcpy(q_next, qc, sizeof(double)*4);
        *res = NAN; *band = BAND_BREAK; *ok = 0; return ST_RESET;
    }

    double te[4], pbe[4], dg[4], dp[4], pp[4], gp[4], hpc[4], hp[4],
           cp[4], ct[4], npr[4], raw[4], sd[4], qr[4];
    hemi(qc, tg, te); hemi(qc, pb, pbe);
    for (int i = 0; i < 4; i++){
        dg[i] = te[i] - qc[i]; dp[i] = pbe[i] - qc[i];
        ct[i] = dg[i] / d_core;
    }
    qproject(qc, dp, pp);
    qproject(qc, dg, gp);
    qsign_perm(qc, hpc); qproject(qc, hpc, hp);
    qproject(qc, ct, cp);
    qproject(qc, nz, npr);

    for (int i = 0; i < 4; i++)
        raw[i] = P[0]*hp[i] + P[1]*pp[i] + P[2]*gp[i] - P[3]*cp[i] + P[4]*npr[i];

    double n_raw = qnorm(raw);
    if (!isfinite(n_raw)){
        memcpy(q_next, qc, sizeof(double)*4);
        *res = NAN; *band = BAND_BREAK; *ok = 0;
        return ST_RESET;
    }
    if (n_raw > EPS) qnormalize(raw, sd);
    else { sd[0]=sd[1]=sd[2]=sd[3]=0.0; }

    for (int i = 0; i < 4; i++) qr[i] = qc[i] + P[7]*sd[i];
    qnormalize(qr, q_next);

    double r = fabs(qnorm(q_next) - 1.0);
    int b = court(r);
    double comp = 1.0 - r; if (comp < 0.0) comp = 0.0;
    *res = r; *band = b; *ok = (b <= BAND_WATCH);
    int st = ST_OK;
    if (comp < MINCOMP){ st = ST_RESET; *ok = 0; }
    return st;
}

static int selftest(void){
    if (court(NAN) != BAND_BREAK) return 1;
    double z[4] = {0,0,0,0}, id[4]; qnormalize(z, id);
    if (id[0] != 1.0 || id[1] || id[2] || id[3]) return 1;

    double nanq[4] = {1,0,0,0}, nant[4] = {NAN,0,0,0}, zz[4] = {0,0,0,0};
    double qn[4], r; int b, ok, st;
    st = guarded_step(nanq, zz, zz, nant, zz, DEF_P, qn, &r, &b, &ok);
    if (st != ST_NO_INFO || ok || qn[0] != 1.0) return 1;
    double ghost[4] = {2,0,0,0};
    st = guarded_step(nanq, zz, zz, ghost, zz, DEF_P, qn, &r, &b, &ok);
    if (st != ST_RESET || ok) return 1;

    uint32_t u = 12345;
    double q[4], v[4], tgt[4], pb[4];
    for (int i = 0; i < 4; i++) q[i] = draw(&u);
    for (int i = 0; i < 4; i++) v[i] = draw(&u);
    for (int i = 0; i < 4; i++) tgt[i] = draw(&u);
    qnormalize(q, q); qnormalize(v, v); qnormalize(tgt, tgt);
    memcpy(pb, q, sizeof(q));

    double best = INFINITY;
    for (int s = 0; s < 64; s++){
        double noise[4];
        for (int i = 0; i < 4; i++) noise[i] = draw(&u);
        double rn[4]; int bb, ook;
        st = guarded_step(q, v, pb, tgt, noise, DEF_P, rn, &r, &bb, &ook);
        seal_d(rn[0]); seal_d(rn[1]); seal_d(rn[2]); seal_d(rn[3]);
        seal_d(r); seal((uint8_t)bb);
        double dv[4]; for (int i = 0; i < 4; i++) dv[i] = rn[i] - q[i];
        qclip(dv, DEF_P[6], v);
        if (r < best){ best = r; memcpy(pb, rn, sizeof(rn)); }
        memcpy(q, rn, sizeof(rn));
    }
    if (FNV != GOLDEN){
        fprintf(stderr, "DIGEST_DRIFT c got=%016llx want=a9a4ed1e54da45c7\n",
                (unsigned long long)FNV);
        return 1;
    }
    printf("TAU_CORE_SELFTEST_OK c digest=%016llx steps=64\n", (unsigned long long)FNV);
    return 0;
}

int main(int argc, char **argv){
    const char *m = argc > 1 ? argv[1] : "--selftest";
    if (!strcmp(m, "--ping")){ printf("PONG\n"); return 0; }
    if (!strcmp(m, "--selftest")) return selftest();
    if (!strcmp(m, "--step")){
        double in[32];
        if (fread(in, sizeof(double), 32, stdin) != 32) return 2;
        double qn[4], r; int b, ok;
        int st = guarded_step(in, in+4, in+8, in+12, in+16, in+20, qn, &r, &b, &ok);
        uint8_t out[51]; int p = 0;
        double all[5] = {qn[0], qn[1], qn[2], qn[3], r};
        for (int i = 0; i < 5; i++){
            uint64_t u; memcpy(&u, &all[i], 8);
            for (int k = 0; k < 8; k++) out[p++] = (uint8_t)(u >> (8*k));
        }
        out[p++] = (uint8_t)b;
        out[p++] = (uint8_t)st;
        out[p++] = (uint8_t)(ok ? 1 : 0);
        FNV = 0xCBF29CE484222325ULL;
        for (int i = 0; i < 43; i++) seal(out[i]);
        uint8_t dg[8]; uint64_t h = FNV;
        for (int k = 7; k >= 0; k--) dg[k] = (uint8_t)(h >> (8*(7-k)));
        fwrite(out, 1, 43, stdout); fwrite(dg, 1, 8, stdout);
        return 0;
    }
    fprintf(stderr, "unknown mode\n"); return 2;
}
