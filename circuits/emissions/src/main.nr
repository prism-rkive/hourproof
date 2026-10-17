// HourProof emissions circuit (carbon-aware mode; the carbon kill test's circuit with the shared commitment).
//   private : load[168] (kWh, metered by the data hub), salt
//   public  : threshold_bps, cap_kg, cert[168] (kWh cancelled per hour) and intensity[168] (g/kWh, posted by
//             the intensity oracle), all rebuilt on-chain by ClaimManager
//   output  : commitment to the load (hp_lib::commit_load: the SAME data-hub attestation serves both proofs)
// Statement: sum_h min(load_h, cert_h) * 10000 >= threshold_bps * sum_h load_h
//        AND sum_h (load_h - min(load_h, cert_h)) * intensity_h <= cap_kg * 1000   (residual, grams)
use hp_lib::{commit_load, HOURS};

fn main(
    load: [u32; HOURS],
    salt: Field,
    threshold_bps: pub u32,
    cap_kg: pub u64,
    cert: pub [u32; HOURS],
    intensity: pub [u32; HOURS],
) -> pub Field {
    assert(threshold_bps <= 10000);
    let mut matched: u64 = 0;
    let mut total: u64 = 0;
    let mut resid_g: u64 = 0;
    for i in 0..HOURS {
        let l = load[i] as u64;
        let c = cert[i] as u64;
        let m = if c < l { c } else { l };
        matched += m;
        total += l;
        resid_g += (l - m) * (intensity[i] as u64);
    }
    assert(total > 0);
    assert(matched * 10000 >= (threshold_bps as u64) * total);
    assert(resid_g <= cap_kg * 1000);
    commit_load(load, salt)
}

// 100 kWh every hour; certificates cover all of it in even hours and half of it in odd hours (75.00 %);
// 120 g/kWh everywhere -> residual = 84 h x 50 kWh x 120 g = 504,000 g = 504 kg exactly
fn half_covered() -> ([u32; HOURS], [u32; HOURS], [u32; HOURS]) {
    let mut load = [0; HOURS];
    let mut cert = [0; HOURS];
    for i in 0..HOURS {
        load[i] = 100;
        cert[i] = if i % 2 == 0 { 100 } else { 50 };
    }
    (load, cert, [120; HOURS])
}

#[test]
fn proves_exact_cap_and_threshold() {
    let (load, cert, intensity) = half_covered();
    let _ = main(load, 7, 7500, 504, cert, intensity);
}

#[test(should_fail)]
fn rejects_cap_one_kg_lower() {
    let (load, cert, intensity) = half_covered();
    let _ = main(load, 7, 7500, 503, cert, intensity);
}

#[test(should_fail)]
fn rejects_threshold_one_basis_point_higher() {
    let (load, cert, intensity) = half_covered();
    let _ = main(load, 7, 7501, 504, cert, intensity);
}

#[test]
fn cap_is_rounded_up_to_whole_kg() {
    let (load, cert, mut intensity) = half_covered();
    intensity[1] = 121; // + 50 g: residual 504,050 g -> the smallest provable cap is 505 kg
    let _ = main(load, 7, 7500, 505, cert, intensity);
}

#[test(should_fail)]
fn rounding_cannot_hide_grams() {
    let (load, cert, mut intensity) = half_covered();
    intensity[1] = 121;
    let _ = main(load, 7, 7500, 504, cert, intensity);
}

#[test]
fn surplus_never_counts() {
    // huge surplus in half the hours, nothing in the other half: residual is the uncovered half only
    let mut load = [0; HOURS];
    let mut cert = [0; HOURS];
    for i in 0..HOURS {
        load[i] = 100;
        cert[i] = if i < 84 { 1000 } else { 0 };
    }
    let _ = main(load, 7, 5000, 84 * 100 * 120 / 1000, cert, [120; HOURS]);
}

#[test(should_fail)]
fn surplus_cannot_offset_residual() {
    let mut load = [0; HOURS];
    let mut cert = [0; HOURS];
    for i in 0..HOURS {
        load[i] = 100;
        cert[i] = if i < 84 { 1000 } else { 0 };
    }
    let _ = main(load, 7, 5000, 84 * 100 * 120 / 1000 - 1, cert, [120; HOURS]);
}

#[test]
fn zero_intensity_hours_add_nothing() {
    // every unmatched hour has intensity 0: the residual is exactly 0 kg
    let (load, cert, _) = half_covered();
    let mut intensity = [0; HOURS];
    for i in 0..HOURS {
        intensity[i] = if i % 2 == 0 { 250 } else { 0 };
    }
    let _ = main(load, 7, 7500, 0, cert, intensity);
}

#[test(should_fail)]
fn threshold_above_100_percent_rejected() {
    let load = [100; HOURS];
    let _ = main(load, 7, 10001, 0, load, [0; HOURS]);
}

#[test]
fn commitment_matches_load_commit() {
    // the output is the data hub's commitment (load_commit runs hp_lib::commit_load) ...
    let (load, cert, intensity) = half_covered();
    let out = main(load, 12345, 7500, 504, cert, intensity);
    assert(out == commit_load(load, 12345));
    // ... and equals the kill test's inline Pedersen form (load as Fields, then the salt)
    let mut buf: [Field; HOURS + 1] = [0; HOURS + 1];
    for i in 0..HOURS {
        buf[i] = load[i] as Field;
    }
    buf[HOURS] = 12345;
    assert(out == std::hash::pedersen_hash(buf));
}
