// Run by the metering data hub (never proven on-chain): computes the commitment it attests.
use hp_lib::{commit_load, HOURS};

fn main(load: [u32; HOURS], salt: Field) -> pub Field {
    commit_load(load, salt)
}
