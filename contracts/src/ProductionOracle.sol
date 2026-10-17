// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {HourKey} from "./libraries/HourKey.sol";

/// @title ProductionOracle
/// @notice Hourly metered production (whole MWh) per (zone, hour, asset), posted by an
///         authorised data poster (in the demo: replayed from Energinet's Energi Data Service).
///         Values are write-once: a correction would need a dispute process, not an overwrite.
///         Registries refuse to issue certificates beyond what was produced in that hour.
contract ProductionOracle {
    address public immutable admin;
    mapping(address => bool) public isPoster;
    mapping(bytes32 => uint32) private _mwh;
    mapping(bytes32 => bool) public isPosted;

    event PosterSet(address indexed poster, bool allowed);
    event ProductionPosted(bytes32 indexed key, bytes32 zone, uint64 hourStartUtc, bytes32 asset, uint32 mwh, address poster);

    error NotAdmin();
    error NotPoster(address caller);
    error LengthMismatch();
    error AlreadyPosted(bytes32 key);
    error NotPosted(bytes32 key);

    constructor() {
        admin = msg.sender;
    }

    function setPoster(address poster, bool allowed) external {
        if (msg.sender != admin) revert NotAdmin();
        isPoster[poster] = allowed;
        emit PosterSet(poster, allowed);
    }

    function post(bytes32 zone, bytes32 asset, uint64[] calldata hourStarts, uint32[] calldata mwh) external {
        if (!isPoster[msg.sender]) revert NotPoster(msg.sender);
        if (hourStarts.length != mwh.length) revert LengthMismatch();
        for (uint256 i; i < hourStarts.length; ++i) {
            bytes32 key = HourKey.compute(zone, hourStarts[i], asset);
            if (isPosted[key]) revert AlreadyPosted(key);
            isPosted[key] = true;
            _mwh[key] = mwh[i];
            emit ProductionPosted(key, zone, hourStarts[i], asset, mwh[i], msg.sender);
        }
    }

    /// @return mwh the posted production; reverts if nothing was posted for that hour
    function productionOf(bytes32 key) external view returns (uint32 mwh) {
        if (!isPosted[key]) revert NotPosted(key);
        return _mwh[key];
    }
}
