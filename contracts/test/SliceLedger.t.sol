// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {SliceLedger} from "../src/SliceLedger.sol";

contract SliceLedgerTest is Test {
    SliceLedger ledger;
    address regA = makeAddr("regA");
    address regB = makeAddr("regB");
    bytes32 constant KEY = keccak256("bucket");

    function setUp() public {
        ledger = new SliceLedger();
        ledger.setRegistry(regA, true);
        ledger.setRegistry(regB, true);
    }

    function test_overlapAcrossRegistriesReverts() public {
        vm.prank(regA);
        ledger.spend(KEY, 0, 50, "a");
        vm.prank(regB);
        vm.expectPartialRevert(SliceLedger.SliceAlreadyClaimed.selector);
        ledger.spend(KEY, 40, 20, "b");
    }

    function test_adjacentRangesOk() public {
        vm.prank(regA);
        ledger.spend(KEY, 0, 50, "a");
        vm.prank(regB);
        ledger.spend(KEY, 50, 20, "b");
        assertEq(ledger.spentCount(KEY), 70);
        assertTrue(ledger.isSpent(KEY, 69));
        assertFalse(ledger.isSpent(KEY, 70));
    }

    function test_onlyRegistries() public {
        vm.expectRevert(abi.encodeWithSelector(SliceLedger.NotRegistry.selector, address(this)));
        ledger.spend(KEY, 0, 1, "x");
    }

    function test_onlyAdminSetsRegistries() public {
        vm.prank(regA);
        vm.expectRevert(SliceLedger.NotAdmin.selector);
        ledger.setRegistry(regA, false);
    }

    function test_emptyRangeReverts() public {
        vm.prank(regA);
        vm.expectRevert(SliceLedger.EmptyRange.selector);
        ledger.spend(KEY, 5, 0, "x");
    }

    function test_wordBoundaries() public {
        vm.prank(regA);
        ledger.spend(KEY, 250, 300, "a"); // spans words 0,1,2
        vm.startPrank(regB);
        vm.expectPartialRevert(SliceLedger.SliceAlreadyClaimed.selector);
        ledger.spend(KEY, 549, 1, "b");
        ledger.spend(KEY, 550, 1, "c");
        vm.stopPrank();
    }

    /// The core property: the second spend reverts if and only if the ranges overlap.
    function testFuzz_revertIffOverlap(uint16 f1, uint8 c1, uint16 f2, uint8 c2) public {
        uint32 a = uint32(f1) % 3000;
        uint32 n = uint32(c1) % 255 + 1;
        uint32 b = uint32(f2) % 3000;
        uint32 m = uint32(c2) % 255 + 1;
        vm.prank(regA);
        ledger.spend(KEY, a, n, "a");
        bool overlap = a < b + m && b < a + n;
        vm.prank(regB);
        if (overlap) vm.expectPartialRevert(SliceLedger.SliceAlreadyClaimed.selector);
        ledger.spend(KEY, b, m, "b");
    }
}
