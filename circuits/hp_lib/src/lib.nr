// Shared definitions for the HourProof circuits. Both the data hub (load_commit) and the
// buyer's prover (coverage) MUST use this exact commitment, or attestation and proof diverge.
use std::hash::pedersen_hash;

pub global HOURS: u32 = 168;

/// Hiding commitment to an hourly load profile (kWh per hour) with a random salt.
pub fn commit_load(load: [u32; HOURS], salt: Field) -> Field {
    let mut buf: [Field; HOURS + 1] = [0; HOURS + 1];
    for i in 0..HOURS {
        buf[i] = load[i] as Field;
    }
    buf[HOURS] = salt;
    pedersen_hash(buf)
}

/// sum_h min(load_h, cert_h) and sum_h load_h, in kWh (u64: no overflow for 168 x u32)
pub fn coverage(load: [u32; HOURS], cert: [u32; HOURS]) -> (u64, u64) {
    let mut matched: u64 = 0;
    let mut total: u64 = 0;
    for i in 0..HOURS {
        let l = load[i] as u64;
        let c = cert[i] as u64;
        matched += if c < l { c } else { l };
        total += l;
    }
    (matched, total)
}
