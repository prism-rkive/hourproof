// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {HourProofBase} from "./Base.t.sol";
import {ClaimManager} from "../src/ClaimManager.sol";
import {CertRegistry} from "../src/CertRegistry.sol";
import {IZKVerifier} from "../src/interfaces/IZKVerifier.sol";

/// End-to-end with the REAL UltraHonk verifier and a REAL proof over real Danish data.
/// Needs `make zk` (or `python -m hourproof zk fixture`) to have generated
///   src/generated/HonkVerifier.sol and test/fixtures/zk/fixture.json.
/// Skipped (not failed) when the fixture is absent.
contract HonkIntegrationTest is HourProofBase {
    string constant FIXTURE = "test/fixtures/zk/fixture.json";
    IZKVerifier honk;
    uint64 window;
    uint32 threshold;
    bytes proof;
    uint256 claimId;

    function setUp() public override {
        super.setUp();
        if (!vm.exists(FIXTURE)) return;
        honk = IZKVerifier(deployCode("HonkVerifier.sol:HonkVerifier"));
        cm.setVerifier(honk);
        string memory j = vm.readFile(FIXTURE);
        window = uint64(vm.parseJsonUint(j, ".window_start"));
        threshold = uint32(vm.parseJsonUint(j, ".threshold_bps"));
        proof = vm.parseJsonBytes(j, ".proof");
        bytes32 commitment = vm.parseJsonBytes32(j, ".load_commitment");
        uint256[] memory certs = vm.parseJsonUintArray(j, ".cert_mwh");
        require(certs.length == 168, "fixture: need 168 hours");

        // production for the window (fixture window may differ from the base fixture's week)
        if (window != WEEK) {
            uint64[] memory hrs = new uint64[](168);
            uint32[] memory v = new uint32[](168);
            for (uint256 i; i < 168; ++i) {
                hrs[i] = window + uint64(i) * H;
                v[i] = uint32(certs[i] + 1);
            }
            vm.prank(poster);
            oracle.post(ZONE, ASSET, hrs, v);
        }
        uint256 n;
        for (uint256 i; i < 168; ++i) if (certs[i] > 0) n++;
        CertRegistry.CertInput[] memory b = new CertRegistry.CertInput[](n);
        uint256 k;
        for (uint256 i; i < 168; ++i) {
            if (certs[i] == 0) continue;
            b[k++] = CertRegistry.CertInput(ZONE, ASSET, window + uint64(i) * H, 0, uint32(certs[i]), buyer);
        }
        uint256 first = regA.issueBatch(ISSUER_A, b, hex"01");
        uint256[] memory ids = new uint256[](n);
        for (uint256 i; i < n; ++i) ids[i] = first + i;
        vm.startPrank(buyer);
        claimId = cm.openClaim(window);
        regA.cancelBatch(ids, claimId, "zk-fixture");
        vm.stopPrank();
        vm.prank(hub);
        cm.attestLoad(buyer, window, commitment);
    }

    modifier needsFixture() {
        if (!vm.exists(FIXTURE)) {
            vm.skip(true);
        }
        _;
    }

    function test_realProofAccepted() public needsFixture {
        vm.prank(buyer);
        uint256 g = gasleft();
        cm.submitProof(claimId, threshold, proof);
        emit log_named_uint("gas: submitProof incl. UltraHonk verify (170 public inputs)", g - gasleft());
        assertEq(cm.bestProvenBps(buyer, window), threshold);
    }

    function test_realProofCannotClaimMore() public needsFixture {
        vm.prank(buyer);
        vm.expectRevert(ClaimManager.ProofRejected.selector);
        cm.submitProof(claimId, threshold + 1, proof);
    }

    function test_realProofNotTransferableToAnotherClaim() public needsFixture {
        // another buyer with its own attestation cannot reuse the proof
        vm.prank(hub);
        cm.attestLoad(ghostBuyer, window, bytes32(uint256(12345)));
        vm.prank(ghostBuyer);
        uint256 other = cm.openClaim(window);
        vm.prank(ghostBuyer);
        vm.expectRevert(ClaimManager.ProofRejected.selector);
        cm.submitProof(other, threshold, proof);
    }
}
