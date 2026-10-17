// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title IntensityOracle
/// @notice Hourly average grid CO2 intensity (whole g/kWh) per (zone, hour), posted by an authorised oracle
///         (in the demo: replayed from Energinet's DeclarationGridEmission, location-based, 125 % method).
///         Values are write-once: a later revision (e.g. Energinet's Final after the Initial version) needs a
///         dispute process, not an overwrite. ClaimManager reads these values to rebuild the emissions proof's
///         public intensity vector, so a prover cannot substitute a cleaner one.
contract IntensityOracle {
    uint64 internal constant HOUR = 3600;
    /// @notice No hourly grid average anywhere comes near this; it bounds a fat-fingered or hostile post.
    uint32 public constant MAX_G_PER_KWH = 2000;

    struct Entry {
        uint32 gPerKwh;
        bool posted;
    }

    address public immutable admin;
    mapping(address => bool) public isOracle;
    mapping(bytes32 => mapping(uint64 => Entry)) private _entries; // zone => hourStartUtc => intensity

    event OracleSet(address indexed oracle, bool allowed);
    event IntensityPosted(bytes32 indexed zone, uint64 indexed hourStartUtc, uint32 gPerKwh, address oracle);

    error NotAdmin();
    error NotOracle(address caller);
    error LengthMismatch();
    error NotHourAligned(uint64 hourStartUtc);
    error AlreadyPosted(bytes32 zone, uint64 hourStartUtc);
    error IntensityOutOfRange(uint64 hourStartUtc, uint32 gPerKwh);
    error NotPosted(bytes32 zone, uint64 hourStartUtc);

    constructor() {
        admin = msg.sender;
    }

    function setOracle(address oracle, bool allowed) external {
        if (msg.sender != admin) revert NotAdmin();
        isOracle[oracle] = allowed;
        emit OracleSet(oracle, allowed);
    }

    function post(bytes32 zone, uint64[] calldata hourStarts, uint32[] calldata gPerKwh) external {
        if (!isOracle[msg.sender]) revert NotOracle(msg.sender);
        if (hourStarts.length != gPerKwh.length) revert LengthMismatch();
        for (uint256 i; i < hourStarts.length; ++i) {
            uint64 h = hourStarts[i];
            uint32 g = gPerKwh[i];
            if (h % HOUR != 0) revert NotHourAligned(h);
            if (g > MAX_G_PER_KWH) revert IntensityOutOfRange(h, g);
            Entry storage e = _entries[zone][h];
            if (e.posted) revert AlreadyPosted(zone, h);
            e.gPerKwh = g;
            e.posted = true;
            emit IntensityPosted(zone, h, g, msg.sender);
        }
    }

    function isPosted(bytes32 zone, uint64 hourStartUtc) external view returns (bool) {
        return _entries[zone][hourStartUtc].posted;
    }

    /// @return gPerKwh the posted intensity; reverts if nothing was posted for that hour
    function intensityOf(bytes32 zone, uint64 hourStartUtc) public view returns (uint32 gPerKwh) {
        Entry storage e = _entries[zone][hourStartUtc];
        if (!e.posted) revert NotPosted(zone, hourStartUtc);
        return e.gPerKwh;
    }

    /// @notice `hours_` consecutive hours from `start`; reverts on the first hour with no posted value.
    function intensities(bytes32 zone, uint64 start, uint256 hours_) external view returns (uint32[] memory v) {
        v = new uint32[](hours_);
        for (uint256 i; i < hours_; ++i) {
            v[i] = intensityOf(zone, start + uint64(i) * HOUR);
        }
    }
}
