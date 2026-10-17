
use std::hash::pedersen_hash;
global N: u32 = 168;
// private: hourly load (kWh), salt.  public: certificates (kWh), grid intensity (g/kWh), coverage bar, emissions cap (kg)
// proves: coverage >= threshold AND unmatched (residual) emissions <= cap, and outputs the load commitment
fn main(load: [u32; N], salt: Field, threshold_bps: pub u32, cap_kg: pub u64, cert: pub [u32; N], intensity: pub [u32; N]) -> pub Field {
    let mut matched: u64 = 0; let mut total: u64 = 0; let mut resid_g: u64 = 0;
    for i in 0..N {
        let l = load[i] as u64; let c = cert[i] as u64;
        let m = if c < l { c } else { l };
        matched += m; total += l;
        resid_g += (l - m) * (intensity[i] as u64);
    }
    assert(total > 0);
    assert(matched * 10000 >= (threshold_bps as u64) * total);
    assert(resid_g <= cap_kg * 1000);
    let mut buf: [Field; N + 1] = [0; N + 1];
    for i in 0..N { buf[i] = load[i] as Field; }
    buf[N] = salt;
    pedersen_hash(buf)
}
