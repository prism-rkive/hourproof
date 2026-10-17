// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title SliceLedger
/// @notice The shared, append-only record of which MWh slices of each physical
///         (zone, hour, asset) bucket have been cancelled, by ANY registry.
///         Slice i of a bucket is the i-th MWh produced in that hour. A slice can be
///         cancelled (claimed) exactly once across all registries: overlapping
///         cancellations revert. This is the double-counting stop.
contract SliceLedger {
    address public immutable admin;
    mapping(address => bool) public isRegistry;
    /// @dev key => word index => bitmap of 256 slices
    mapping(bytes32 => mapping(uint256 => uint256)) public spentWord;
    mapping(bytes32 => uint256) public spentCount;

    event RegistrySet(address indexed registry, bool allowed);
    event SlicesSpent(bytes32 indexed key, uint32 first, uint32 count, address indexed registry, bytes32 claimRef);

    error NotAdmin();
    error NotRegistry(address caller);
    error EmptyRange();
    error SliceAlreadyClaimed(bytes32 key, uint256 word, uint256 overlapMask);

    constructor() {
        admin = msg.sender;
    }

    function setRegistry(address registry, bool allowed) external {
        if (msg.sender != admin) revert NotAdmin();
        isRegistry[registry] = allowed;
        emit RegistrySet(registry, allowed);
    }

    /// @notice Mark slices [first, first + count) of `key` as spent. Reverts on any overlap.
    function spend(bytes32 key, uint32 first, uint32 count, bytes32 claimRef) external {
        if (!isRegistry[msg.sender]) revert NotRegistry(msg.sender);
        if (count == 0) revert EmptyRange();
        uint256 lo = first;
        uint256 hi = uint256(first) + count; // exclusive
        uint256 lastWord = (hi - 1) >> 8;
        for (uint256 w = lo >> 8; w <= lastWord; ++w) {
            uint256 a = w == (lo >> 8) ? lo & 255 : 0;
            uint256 b = w == lastWord ? ((hi - 1) & 255) + 1 : 256;
            uint256 mask = b == 256 ? type(uint256).max << a : ((uint256(1) << b) - 1) ^ ((uint256(1) << a) - 1);
            uint256 cur = spentWord[key][w];
            if (cur & mask != 0) revert SliceAlreadyClaimed(key, w, cur & mask);
            spentWord[key][w] = cur | mask;
        }
        spentCount[key] += count;
        emit SlicesSpent(key, first, count, msg.sender, claimRef);
    }

    function isSpent(bytes32 key, uint32 slice) external view returns (bool) {
        return (spentWord[key][slice >> 8] >> (slice & 255)) & 1 == 1;
    }
}
