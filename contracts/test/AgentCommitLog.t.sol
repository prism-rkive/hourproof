// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {AgentCommitLog} from "../src/AgentCommitLog.sol";

contract AgentCommitLogTest is Test {
    AgentCommitLog agentLog;
    bytes32 constant AGENT = "hourproof-agent-v1";

    function setUp() public {
        agentLog = new AgentCommitLog();
        vm.warp(1_800_000_000);
    }

    function test_commitBeforeDayIsEarly() public {
        bytes memory plan = bytes('{"day":"x","shift":[1,2,3]}');
        uint64 day = uint64(block.timestamp + 3600);
        agentLog.commit(AGENT, day, keccak256(plan));
        (bytes32 h, uint64 at, bool early, bool revealed) = agentLog.entries(address(this), AGENT, day);
        assertEq(h, keccak256(plan));
        assertEq(at, block.timestamp);
        assertTrue(early);
        assertFalse(revealed);
        agentLog.reveal(AGENT, day, plan);
        (,,, revealed) = agentLog.entries(address(this), AGENT, day);
        assertTrue(revealed);
    }

    function test_commitAfterDayStartIsMarkedLate() public {
        uint64 day = uint64(block.timestamp - 1);
        agentLog.commit(AGENT, day, keccak256("p"));
        (,, bool early,) = agentLog.entries(address(this), AGENT, day);
        assertFalse(early);
    }

    function test_cannotRewritePlan() public {
        uint64 day = uint64(block.timestamp + 3600);
        agentLog.commit(AGENT, day, keccak256("p1"));
        vm.expectRevert(AgentCommitLog.AlreadyCommitted.selector);
        agentLog.commit(AGENT, day, keccak256("p2"));
        vm.expectRevert(AgentCommitLog.HashMismatch.selector);
        agentLog.reveal(AGENT, day, "p2");
    }

    function test_revealNeedsCommit() public {
        vm.expectRevert(AgentCommitLog.NotCommitted.selector);
        agentLog.reveal(AGENT, 1, "p");
    }
}
