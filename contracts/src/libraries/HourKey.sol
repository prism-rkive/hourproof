// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @notice One canonical key for a physical (zone, hour, asset) energy bucket.
///         Every contract (oracle, ledger, registries) derives the same key from
///         physical attributes, so two registries describing the same energy collide.
library HourKey {
    uint64 internal constant HOUR = 3600;

    error NotHourAligned(uint64 hour);

    function compute(bytes32 zone, uint64 hourStartUtc, bytes32 asset) internal pure returns (bytes32) {
        if (hourStartUtc % HOUR != 0) revert NotHourAligned(hourStartUtc);
        return keccak256(abi.encode("HOURPROOF/v1/hour", zone, hourStartUtc, asset));
    }
}
