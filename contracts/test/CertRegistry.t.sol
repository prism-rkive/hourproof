// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {HourProofBase} from "./Base.t.sol";
import {CertRegistry} from "../src/CertRegistry.sol";
import {SliceLedger} from "../src/SliceLedger.sol";
import {ProductionOracle} from "../src/ProductionOracle.sol";
import {HourKey} from "../src/libraries/HourKey.sol";

contract CertRegistryTest is HourProofBase {
    function test_issueWithinProduction() public {
        uint256 id = regA.issueBatch(ISSUER_A, _one(WEEK, 0, 1000, buyer), hex"01");
        (, uint64 hour, uint32 first, uint32 count, address owner, bool cancelled) = regA.certs(id);
        assertEq(hour, WEEK);
        assertEq(first, 0);
        assertEq(count, 1000);
        assertEq(owner, buyer);
        assertFalse(cancelled);
    }

    function test_cannotIssueBeyondMeteredProduction() public {
        vm.expectPartialRevert(CertRegistry.ExceedsProduction.selector);
        regA.issueBatch(ISSUER_A, _one(WEEK, 900, 101, buyer), hex"01");
    }

    function test_cannotIssueForUnpostedHour() public {
        vm.expectPartialRevert(ProductionOracle.NotPosted.selector);
        regA.issueBatch(ISSUER_A, _one(WEEK + 168 * H, 0, 1, buyer), hex"01");
    }

    function test_forgedIssuerSignatureRejected() public {
        vm.expectRevert(abi.encodeWithSelector(CertRegistry.BadIssuerSignature.selector, ISSUER_A));
        regA.issueBatch(ISSUER_A, _one(WEEK, 0, 1, buyer), hex"00");
    }

    function test_unknownOrDisabledIssuer() public {
        vm.expectRevert(abi.encodeWithSelector(CertRegistry.UnknownIssuer.selector, bytes32("nobody")));
        regA.issueBatch("nobody", _one(WEEK, 0, 1, buyer), hex"01");
        regA.setIssuerActive(ISSUER_A, false);
        vm.expectRevert(abi.encodeWithSelector(CertRegistry.UnknownIssuer.selector, ISSUER_A));
        regA.issueBatch(ISSUER_A, _one(WEEK, 0, 1, buyer), hex"01");
    }

    function test_nonceChangesTheSignedMessage() public {
        CertRegistry.CertInput[] memory b = _one(WEEK, 0, 1, buyer);
        bytes memory m0 = regA.batchMessage(ISSUER_A, b);
        regA.issueBatch(ISSUER_A, b, hex"01");
        bytes memory m1 = regA.batchMessage(ISSUER_A, b);
        assertTrue(keccak256(m0) != keccak256(m1), "replayable signature");
    }

    function test_onlyOperatorRegistersIssuers() public {
        vm.prank(buyer);
        vm.expectRevert(CertRegistry.NotOperator.selector);
        regA.registerIssuer("x", address(1));
    }

    /// Headline: the same physical MWh issued by two registries can be claimed only once.
    function test_crossRegistryDoubleClaimReverts() public {
        uint256 a = regA.issueBatch(ISSUER_A, _one(WEEK, 0, 50, buyer), hex"01");
        uint256 b = regB.issueBatch(ISSUER_B, _one(WEEK, 40, 20, ghostBuyer), hex"01");
        vm.prank(buyer);
        regA.cancelBatch(_ids(a), 0, "claim-A");
        vm.prank(ghostBuyer);
        vm.expectPartialRevert(SliceLedger.SliceAlreadyClaimed.selector);
        regB.cancelBatch(_ids(b), 0, "claim-B");
    }

    function test_cancelTwiceReverts() public {
        uint256 a = regA.issueBatch(ISSUER_A, _one(WEEK, 0, 5, buyer), hex"01");
        vm.startPrank(buyer);
        regA.cancelBatch(_ids(a), 0, "c");
        vm.expectRevert(abi.encodeWithSelector(CertRegistry.AlreadyCancelled.selector, a));
        regA.cancelBatch(_ids(a), 0, "c");
        vm.stopPrank();
    }

    function test_onlyOwnerCancelsAndTransfers() public {
        uint256 a = regA.issueBatch(ISSUER_A, _one(WEEK, 0, 5, buyer), hex"01");
        vm.prank(ghostBuyer);
        vm.expectRevert(abi.encodeWithSelector(CertRegistry.NotOwner.selector, a));
        regA.cancelBatch(_ids(a), 0, "c");
        vm.prank(buyer);
        regA.transfer(a, ghostBuyer);
        vm.prank(ghostBuyer);
        regA.cancelBatch(_ids(a), 0, "c");
    }

    function test_cancelIntoClaimRecordsHourlyMWh() public {
        uint256 a = regA.issueBatch(ISSUER_A, _one(WEEK + 5 * H, 0, 42, buyer), hex"01");
        vm.startPrank(buyer);
        uint256 claimId = cm.openClaim(WEEK);
        regA.cancelBatch(_ids(a), claimId, "c");
        vm.stopPrank();
        assertEq(cm.certMWh(claimId, 5), 42);
    }

    function test_ledgerKeyMatchesOracleKey() public view {
        assertEq(HourKey.compute(ZONE, WEEK, ASSET), keccak256(abi.encode("HOURPROOF/v1/hour", ZONE, WEEK, ASSET)));
    }
}
