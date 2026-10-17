// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {HourProofBase} from "./Base.t.sol";
import {SustainabilityLinkedNote, IERC20Min} from "../src/SustainabilityLinkedNote.sol";
import {TestUSD} from "../src/TestUSD.sol";
import {IntensityOracle} from "../src/IntensityOracle.sol";
import {IZKVerifier} from "../src/interfaces/IZKVerifier.sol";
import {MockZKVerifier} from "./mocks/Mocks.sol";

/// KPI = residual (unmatched) location-based emissions for the window, proven in zero knowledge.
contract NoteResidualTest is HourProofBase {
    TestUSD usd;
    SustainabilityLinkedNote note;
    IntensityOracle io;
    MockZKVerifier ezk;
    address investor = makeAddr("investor");
    address intensityPoster = makeAddr("intensityPoster");
    uint64 deadline;
    uint64 constant TARGET_KG = 1_500_000; // 1,500 t

    function setUp() public override {
        super.setUp();
        io = new IntensityOracle();
        io.setOracle(intensityPoster, true);
        ezk = new MockZKVerifier();
        cm.setEmissionsVerifier(IZKVerifier(address(ezk)));
        cm.setIntensityOracle(io, ZONE);
        uint64[] memory hrs = new uint64[](168);
        uint32[] memory v = new uint32[](168);
        for (uint256 i; i < 168; ++i) {
            hrs[i] = WEEK + uint64(i) * H;
            v[i] = 150;
        }
        vm.prank(intensityPoster);
        io.post(ZONE, hrs, v);

        usd = new TestUSD();
        deadline = uint64(block.timestamp + 7 days);
        // target residual 1,500 t, base coupon 5.00 %, step-up +1.00 %
        note = new SustainabilityLinkedNote(
            cm,
            IERC20Min(address(usd)),
            buyer,
            WEEK,
            SustainabilityLinkedNote.KpiKind.RESIDUAL_EMISSIONS,
            TARGET_KG,
            500,
            100,
            deadline
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

    function _claim() internal returns (uint256 claimId) {
        uint256 id = regA.issueBatch(ISSUER_A, _one(WEEK, 0, 10, buyer), hex"01");
        vm.startPrank(buyer);
        claimId = cm.openClaim(WEEK);
        regA.cancelBatch(_ids(id), claimId, "c");
        vm.stopPrank();
        vm.prank(hub);
        cm.attestLoad(buyer, WEEK, bytes32(uint256(7)));
    }

    function _proveCap(uint256 claimId, uint64 capKg) internal {
        ezk.expect(hex"01", cm.emissionsPublicInputs(claimId, 0, capKg));
        vm.prank(buyer);
        cm.submitEmissionsProof(claimId, 0, capKg, hex"01");
    }

    function test_kindAndTarget() public view {
        assertEq(uint8(note.kpiKind()), uint8(SustainabilityLinkedNote.KpiKind.RESIDUAL_EMISSIONS));
        assertEq(note.targetResidualKg(), TARGET_KG);
        assertEq(note.targetBps(), 0);
    }

    function test_capAtTargetPaysBaseCoupon() public {
        _proveCap(_claim(), TARGET_KG);
        note.settle(); // before the deadline: allowed because the KPI is met
        assertTrue(note.kpiMet());
        assertEq(note.couponBps(), 500);
        vm.prank(buyer);
        note.fundCoupon();
        vm.prank(investor);
        note.claimCoupon();
        assertEq(usd.balanceOf(investor), 50 ether);
    }

    function test_capOneKgAboveTargetStepsUp() public {
        _proveCap(_claim(), TARGET_KG + 1);
        vm.expectRevert(SustainabilityLinkedNote.TooEarly.selector);
        note.settle();
        vm.warp(deadline);
        note.settle();
        assertFalse(note.kpiMet());
        assertEq(note.couponBps(), 600);
    }

    function test_noProofStepsUpOnlyAfterDeadline() public {
        vm.expectRevert(SustainabilityLinkedNote.TooEarly.selector);
        note.settle();
        vm.warp(deadline);
        note.settle();
        assertFalse(note.kpiMet());
        assertEq(note.couponBps(), 600);
    }

    /// A coverage proof, however high, does not meet a residual-emissions KPI.
    function test_coverageProofDoesNotMeetResidualKpi() public {
        uint256 claimId = _claim();
        zk.expect(hex"02", cm.publicInputs(claimId, 10000));
        vm.prank(buyer);
        cm.submitProof(claimId, 10000, hex"02");
        assertEq(cm.bestProvenBps(buyer, WEEK), 10000);
        vm.expectRevert(SustainabilityLinkedNote.TooEarly.selector);
        note.settle();
    }

    /// Another buyer's proof for the same window does not count for the issuer.
    function test_otherBuyersProofDoesNotCount() public {
        uint256 id = regA.issueBatch(ISSUER_A, _one(WEEK, 10, 10, ghostBuyer), hex"01");
        vm.startPrank(ghostBuyer);
        uint256 claimId = cm.openClaim(WEEK);
        regA.cancelBatch(_ids(id), claimId, "g");
        vm.stopPrank();
        vm.prank(hub);
        cm.attestLoad(ghostBuyer, WEEK, bytes32(uint256(8)));
        ezk.expect(hex"01", cm.emissionsPublicInputs(claimId, 0, 1));
        vm.prank(ghostBuyer);
        cm.submitEmissionsProof(claimId, 0, 1, hex"01");
        vm.expectRevert(SustainabilityLinkedNote.TooEarly.selector);
        note.settle();
    }

    function test_badTargets() public {
        vm.expectRevert(SustainabilityLinkedNote.BadTarget.selector);
        new SustainabilityLinkedNote(
            cm, IERC20Min(address(usd)), buyer, WEEK, SustainabilityLinkedNote.KpiKind.RESIDUAL_EMISSIONS,
            type(uint64).max, 500, 100, deadline
        );
        vm.expectRevert(SustainabilityLinkedNote.BadTarget.selector);
        new SustainabilityLinkedNote(
            cm, IERC20Min(address(usd)), buyer, WEEK, SustainabilityLinkedNote.KpiKind.COVERAGE, 10001, 500, 100, deadline
        );
        vm.expectRevert(SustainabilityLinkedNote.BadTarget.selector);
        new SustainabilityLinkedNote(
            cm, IERC20Min(address(usd)), buyer, WEEK, SustainabilityLinkedNote.KpiKind.COVERAGE, 0, 500, 100, deadline
        );
    }

    function testFuzz_kpiMetIffCapAtOrBelowTarget(uint64 capKg) public {
        capKg = uint64(bound(capKg, 0, 10 * uint256(TARGET_KG)));
        _proveCap(_claim(), capKg);
        vm.warp(deadline);
        note.settle();
        assertEq(note.kpiMet(), capKg <= TARGET_KG);
        assertEq(note.couponBps(), capKg <= TARGET_KG ? 500 : 600);
    }
}
