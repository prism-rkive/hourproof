// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {HourProofBase} from "./Base.t.sol";
import {ClaimManager} from "../src/ClaimManager.sol";
import {CertRegistry} from "../src/CertRegistry.sol";

contract ClaimManagerTest is HourProofBase {
    bytes32 constant COMMIT = bytes32(uint256(0x1234));
    bytes constant PROOF = hex"c0ffee";

    function _claimWithCerts() internal returns (uint256 claimId) {
        CertRegistry.CertInput[] memory b = new CertRegistry.CertInput[](3);
        b[0] = CertRegistry.CertInput(ZONE, ASSET, WEEK, 0, 10, buyer);
        b[1] = CertRegistry.CertInput(ZONE, ASSET, WEEK + H, 0, 20, buyer);
        b[2] = CertRegistry.CertInput(ZONE, ASSET, WEEK + 167 * H, 0, 30, buyer);
        uint256 first = regA.issueBatch(ISSUER_A, b, hex"01");
        uint256[] memory ids = new uint256[](3);
        for (uint256 i; i < 3; ++i) ids[i] = first + i;
        vm.startPrank(buyer);
        claimId = cm.openClaim(WEEK);
        regA.cancelBatch(ids, claimId, "claim");
        vm.stopPrank();
    }

    function test_publicInputsLayout() public {
        uint256 claimId = _claimWithCerts();
        vm.prank(hub);
        cm.attestLoad(buyer, WEEK, COMMIT);
        bytes32[] memory p = cm.publicInputs(claimId, 7269);
        assertEq(p.length, 170);
        assertEq(uint256(p[0]), 7269);
        assertEq(uint256(p[1]), 10_000); // MWh -> kWh
        assertEq(uint256(p[2]), 20_000);
        assertEq(uint256(p[3]), 0);
        assertEq(uint256(p[168]), 30_000);
        assertEq(p[169], COMMIT);
    }

    function test_validProofRecordsCoverage() public {
        uint256 claimId = _claimWithCerts();
        vm.prank(hub);
        cm.attestLoad(buyer, WEEK, COMMIT);
        zk.expect(PROOF, cm.publicInputs(claimId, 7000));
        vm.prank(buyer);
        cm.submitProof(claimId, 7000, PROOF);
        assertEq(cm.bestProvenBps(buyer, WEEK), 7000);
        (,, uint32 proven, uint32 cancelled) = cm.claims(claimId);
        assertEq(proven, 7000);
        assertEq(cancelled, 60);
    }

    /// The prover cannot claim a higher threshold than the one its proof was made for.
    function test_higherThresholdRejected() public {
        uint256 claimId = _claimWithCerts();
        vm.prank(hub);
        cm.attestLoad(buyer, WEEK, COMMIT);
        zk.expect(PROOF, cm.publicInputs(claimId, 7000));
        vm.prank(buyer);
        vm.expectRevert(ClaimManager.ProofRejected.selector);
        cm.submitProof(claimId, 7001, PROOF);
    }

    /// A proof made against other certificates fails, because the contract rebuilds the
    /// certificate vector from its own records.
    function test_proofForDifferentCertsRejected() public {
        uint256 claimId = _claimWithCerts();
        vm.prank(hub);
        cm.attestLoad(buyer, WEEK, COMMIT);
        bytes32[] memory forged = cm.publicInputs(claimId, 7000);
        forged[3] = bytes32(uint256(999_000)); // pretend an extra 999 MWh in hour 2
        zk.expect(PROOF, forged);
        vm.prank(buyer);
        vm.expectRevert(ClaimManager.ProofRejected.selector);
        cm.submitProof(claimId, 7000, PROOF);
    }

    function test_needsDataHubAttestation() public {
        uint256 claimId = _claimWithCerts();
        vm.expectRevert(abi.encodeWithSelector(ClaimManager.NoLoadAttestation.selector, buyer, WEEK));
        vm.prank(buyer);
        cm.submitProof(claimId, 7000, PROOF);
    }

    function test_attestationIsWriteOnceAndHubOnly() public {
        vm.expectRevert(abi.encodeWithSelector(ClaimManager.NotDataHub.selector, address(this)));
        cm.attestLoad(buyer, WEEK, COMMIT);
        vm.startPrank(hub);
        cm.attestLoad(buyer, WEEK, COMMIT);
        vm.expectRevert(abi.encodeWithSelector(ClaimManager.AlreadyAttested.selector, buyer, WEEK));
        cm.attestLoad(buyer, WEEK, bytes32(uint256(1)));
        vm.stopPrank();
    }

    function test_onlyBuyerSubmits() public {
        uint256 claimId = _claimWithCerts();
        vm.prank(hub);
        cm.attestLoad(buyer, WEEK, COMMIT);
        vm.prank(ghostBuyer);
        vm.expectRevert(abi.encodeWithSelector(ClaimManager.NotBuyer.selector, claimId));
        cm.submitProof(claimId, 7000, PROOF);
    }

    function test_badThreshold() public {
        uint256 claimId = _claimWithCerts();
        vm.startPrank(buyer);
        vm.expectRevert(abi.encodeWithSelector(ClaimManager.BadThreshold.selector, uint32(10001)));
        cm.submitProof(claimId, 10001, PROOF);
        vm.expectRevert(abi.encodeWithSelector(ClaimManager.BadThreshold.selector, uint32(0)));
        cm.submitProof(claimId, 0, PROOF);
        vm.stopPrank();
    }

    function test_cancellationOutsideWindowReverts() public {
        uint64 late = WEEK + 168 * H;
        uint64[] memory hrs = new uint64[](1);
        uint32[] memory v = new uint32[](1);
        hrs[0] = late;
        v[0] = 10;
        vm.prank(poster);
        oracle.post(ZONE, ASSET, hrs, v);
        uint256 id = regA.issueBatch(ISSUER_A, _one(late, 0, 1, buyer), hex"01");
        vm.startPrank(buyer);
        uint256 claimId = cm.openClaim(WEEK);
        vm.expectRevert(abi.encodeWithSelector(ClaimManager.HourOutsideWindow.selector, late));
        regA.cancelBatch(_ids(id), claimId, "c");
        vm.stopPrank();
    }

    function test_cannotCancelIntoSomeoneElsesClaim() public {
        uint256 id = regA.issueBatch(ISSUER_A, _one(WEEK, 0, 1, ghostBuyer), hex"01");
        vm.prank(buyer);
        uint256 claimId = cm.openClaim(WEEK);
        vm.prank(ghostBuyer);
        vm.expectRevert(abi.encodeWithSelector(ClaimManager.NotBuyer.selector, claimId));
        regA.cancelBatch(_ids(id), claimId, "c");
    }

    function test_unregisteredRegistryCannotRecord() public {
        vm.prank(buyer);
        uint256 claimId = cm.openClaim(WEEK);
        vm.expectRevert(abi.encodeWithSelector(ClaimManager.NotRegistry.selector, address(this)));
        cm.recordCancellation(claimId, buyer, WEEK, 1000);
    }

    function test_windowMustBeHourAligned() public {
        vm.expectRevert(abi.encodeWithSelector(ClaimManager.NotHourAligned.selector, WEEK + 1));
        cm.openClaim(WEEK + 1);
    }
}
