// HourProof coverage circuit.
//   private : load[168] (kWh, metered by the data hub), salt
//   public  : threshold_bps, cert[168] (kWh cancelled per hour, rebuilt on-chain by ClaimManager)
//   output  : commitment to the load (must equal the data hub's on-chain attestation)
// Statement: sum_h min(load_h, cert_h) * 10000 >= threshold_bps * sum_h load_h
use hp_lib::{commit_load, coverage, HOURS};

fn main(load: [u32; HOURS], salt: Field, threshold_bps: pub u32, cert: pub [u32; HOURS]) -> pub Field {
    assert(threshold_bps <= 10000);
    let (matched, total) = coverage(load, cert);
    assert(total > 0);
    assert(matched * 10000 >= (threshold_bps as u64) * total);
    commit_load(load, salt)
}

#[test]
fn proves_exact_coverage() {
    let mut load = [0; HOURS];
    let mut cert = [0; HOURS];
    for i in 0..HOURS {
        load[i] = 100;
        cert[i] = if i % 2 == 0 { 100 } else { 50 };
    }
    let _ = main(load, 7, 7500, cert); // (100 + 50) / 200 = 75.00 %
}

#[test(should_fail)]
fn rejects_overclaim_by_one_basis_point() {
    let mut load = [0; HOURS];
    let mut cert = [0; HOURS];
    for i in 0..HOURS {
        load[i] = 100;
        cert[i] = if i % 2 == 0 { 100 } else { 50 };
    }
    let _ = main(load, 7, 7501, cert);
}

#[test]
fn surplus_hours_do_not_count() {
    let mut load = [0; HOURS];
    let mut cert = [0; HOURS];
    for i in 0..HOURS {
        load[i] = 100;
        cert[i] = if i < 84 { 1000 } else { 0 }; // huge surplus in half the hours
    }
    let _ = main(load, 7, 5000, cert); // still only 50 %
}

#[test(should_fail)]
fn surplus_cannot_buy_more_coverage() {
    let mut load = [0; HOURS];
    let mut cert = [0; HOURS];
    for i in 0..HOURS {
        load[i] = 100;
        cert[i] = if i < 84 { 1000 } else { 0 };
    }
    let _ = main(load, 7, 5001, cert);
}

#[test(should_fail)]
fn threshold_above_100_percent_rejected() {
    let load = [100; HOURS];
    let _ = main(load, 7, 10001, load);
}
