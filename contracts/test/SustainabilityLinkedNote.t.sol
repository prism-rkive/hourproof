// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {HourProofBase} from "./Base.t.sol";
import {SustainabilityLinkedNote, IERC20Min} from "../src/SustainabilityLinkedNote.sol";
import {TestUSD} from "../src/TestUSD.sol";
import {CertRegistry} from "../src/CertRegistry.sol";

contract NoteTest is HourProofBase {
    TestUSD usd;
    SustainabilityLinkedNote note;
    address investor = makeAddr("investor");
    uint64 deadline;

    function setUp() public override {
        super.setUp();
        usd = new TestUSD();
        deadline = uint64(block.timestamp + 7 days);
        // target 70.00 %, base coupon 5.00 %, step-up +1.00 %
        note = new SustainabilityLinkedNote(
            cm, IERC20Min(address(usd)), buyer, WEEK, SustainabilityLinkedNote.KpiKind.COVERAGE, 7000, 500, 100, deadline
        );
        usd.mint(investor, 1_000 ether);
        usd.mint(buyer, 1_000 ether);
        vm.prank(investor);
        usd.approve(address(note), type(uint256).max);
        vm.prank(buyer);
        usd.approve(address(note), type(uint256).max);
        vm.prank(investor);
        note.subscribe(1_000 ether);
    }

    function _prove(uint32 bps) internal {
        uint256 id = regA.issueBatch(ISSUER_A, _one(WEEK, 0, 10, buyer), hex"01");
        vm.startPrank(buyer);
        uint256 claimId = cm.openClaim(WEEK);
        regA.cancelBatch(_ids(id), claimId, "c");
        vm.stopPrank();
        vm.prank(hub);
        cm.attestLoad(buyer, WEEK, bytes32(uint256(7)));
        zk.expect(hex"01", cm.publicInputs(claimId, bps));
        vm.prank(buyer);
        cm.submitProof(claimId, bps, hex"01");
    }

    function test_principalGoesToIssuer() public view {
        assertEq(usd.balanceOf(buyer), 2_000 ether);
        assertEq(note.balanceOf(investor), 1_000 ether);
    }

    function test_kpiMetByProofPaysBaseCoupon() public {
        _prove(7000);
        note.settle();
        assertTrue(note.kpiMet());
        assertEq(note.couponBps(), 500);
        vm.prank(buyer);
        note.fundCoupon();
        vm.prank(investor);
        note.claimCoupon();
        assertEq(usd.balanceOf(investor), 50 ether);
    }

    function test_noProofCannotSettleEarly() public {
        vm.expectRevert(SustainabilityLinkedNote.TooEarly.selector);
        note.settle();
    }

    function test_proofBelowTargetStepsUpAfterDeadline() public {
        _prove(6500);
        vm.expectRevert(SustainabilityLinkedNote.TooEarly.selector);
        note.settle();
        vm.warp(deadline);
        note.settle();
        assertFalse(note.kpiMet());
        assertEq(note.couponBps(), 600);
        vm.prank(buyer);
        note.fundCoupon();
        vm.prank(investor);
        note.claimCoupon();
        assertEq(usd.balanceOf(investor), 60 ether);
    }

    function test_cannotClaimTwiceOrUnfunded() public {
        _prove(7500);
        note.settle();
        vm.prank(investor);
        vm.expectRevert(SustainabilityLinkedNote.Underfunded.selector);
        note.claimCoupon();
        vm.prank(buyer);
        note.fundCoupon();
        vm.startPrank(investor);
        note.claimCoupon();
        vm.expectRevert(SustainabilityLinkedNote.NothingToClaim.selector);
        note.claimCoupon();
        vm.stopPrank();
    }

    function test_onlyIssuerFunds() public {
        _prove(7500);
        note.settle();
        vm.expectRevert(SustainabilityLinkedNote.NotIssuer.selector);
        note.fundCoupon();
    }
}
