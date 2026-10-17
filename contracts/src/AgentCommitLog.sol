// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title AgentCommitLog
/// @notice An AI agent commits the hash of its plan for a delivery day BEFORE the day starts,
///         then reveals it. The chain timestamps the commitment, so a plan cannot be rewritten
///         with hindsight. `early` records whether the commit landed before the day began.
contract AgentCommitLog {
    struct Entry {
        bytes32 planHash;
        uint64 committedAt;
        bool early;
        bool revealed;
    }

    mapping(address => mapping(bytes32 => mapping(uint64 => Entry))) public entries; // committer => agentId => dayStart

    event PlanCommitted(address indexed committer, bytes32 indexed agentId, uint64 indexed dayStart, bytes32 planHash, bool early);
    event PlanRevealed(address indexed committer, bytes32 indexed agentId, uint64 indexed dayStart, bytes plan);

    error AlreadyCommitted();
    error NotCommitted();
    error AlreadyRevealed();
    error HashMismatch();

    function commit(bytes32 agentId, uint64 dayStart, bytes32 planHash) external {
        Entry storage e = entries[msg.sender][agentId][dayStart];
        if (e.committedAt != 0) revert AlreadyCommitted();
        bool early = block.timestamp < dayStart;
        entries[msg.sender][agentId][dayStart] = Entry(planHash, uint64(block.timestamp), early, false);
        emit PlanCommitted(msg.sender, agentId, dayStart, planHash, early);
    }

    function reveal(bytes32 agentId, uint64 dayStart, bytes calldata plan) external {
        Entry storage e = entries[msg.sender][agentId][dayStart];
        if (e.committedAt == 0) revert NotCommitted();
        if (e.revealed) revert AlreadyRevealed();
        if (keccak256(plan) != e.planHash) revert HashMismatch();
        e.revealed = true;
        emit PlanRevealed(msg.sender, agentId, dayStart, plan);
    }
}
