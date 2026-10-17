// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {HourProofBase} from "./Base.t.sol";
import {ClaimManager} from "../src/ClaimManager.sol";
import {CertRegistry} from "../src/CertRegistry.sol";
import {IntensityOracle} from "../src/IntensityOracle.sol";
import {IZKVerifier} from "../src/interfaces/IZKVerifier.sol";
import {MockZKVerifier} from "./mocks/Mocks.sol";

contract ClaimManagerEmissionsTest is HourProofBase {
    bytes32 constant COMMIT = bytes32(uint256(0x1234));
    bytes constant PROOF = hex"c0ffee";
    IntensityOracle io;
    MockZKVerifier ezk;
    address intensityPoster = makeAddr("intensityPoster");

    function setUp() public override {
        super.setUp();
        io = new IntensityOracle();
        io.setOracle(intensityPoster, true);
        ezk = new MockZKVerifier();
        cm.setEmissionsVerifier(IZKVerifier(address(ezk)));
        cm.setIntensityOracle(io, ZONE);
    }

    function _postIntensity(uint256 n) internal {
        uint64[] memory hrs = new uint64[](n);
        uint32[] memory v = new uint32[](n);
        for (uint256 i; i < n; ++i) {
            hrs[i] = WEEK + uint64(i) * H;
            v[i] = uint32(100 + i);
        }
        vm.prank(intensityPoster);
        io.post(ZONE, hrs, v);
    }

    function _claim() internal returns (uint256 claimId) {
        CertRegistry.CertInput[] memory b = new CertRegistry.CertInput[](2);
        b[0] = CertRegistry.CertInput(ZONE, ASSET, WEEK, 0, 10, buyer);
        b[1] = CertRegistry.CertInput(ZONE, ASSET, WEEK + 167 * H, 0, 30, buyer);
        uint256 first = regA.issueBatch(ISSUER_A, b, hex"01");
        uint256[] memory ids = new uint256[](2);
        ids[0] = first;
        ids[1] = first + 1;
        vm.startPrank(buyer);
        claimId = cm.openClaim(WEEK);
        regA.cancelBatch(ids, claimId, "claim");
        vm.stopPrank();
        vm.prank(hub);
        cm.attestLoad(buyer, WEEK, COMMIT);
    }

    function test_publicInputsLayout() public {
        uint256 claimId = _claim();
        _postIntensity(168);
        bytes32[] memory p = cm.emissionsPublicInputs(claimId, 4476, 1_842_700);
        assertEq(p.length, 339);
        assertEq(uint256(p[0]), 4476);
        assertEq(uint256(p[1]), 1_842_700);
        assertEq(uint256(p[2]), 10_000); // hour 0: 10 MWh -> kWh
        assertEq(uint256(p[3]), 0);
        assertEq(uint256(p[169]), 30_000); // hour 167
        assertEq(uint256(p[170]), 100); // intensity hour 0
        assertEq(uint256(p[337]), 267); // intensity hour 167
        assertEq(p[338], COMMIT); // the same attestation as the coverage proof
        // the certificate part and the commitment are exactly the coverage proof's
        bytes32[] memory cov = cm.publicInputs(claimId, 4476);
        for (uint256 i; i < 168; ++i) assertEq(p[i + 2], cov[i + 1]);
        assertEq(p[338], cov[169]);
    }

    function test_validProofRecordsLowestCap() public {
        uint256 claimId = _claim();
        _postIntensity(168);
        assertEq(cm.bestProvenResidualKg(claimId), cm.NO_RESIDUAL_PROOF());
        assertEq(cm.bestResidualKgOf(buyer, WEEK), cm.NO_RESIDUAL_PROOF());
        ezk.expect(PROOF, cm.emissionsPublicInputs(claimId, 0, 900));
        vm.prank(buyer);
        cm.submitEmissionsProof(claimId, 0, 900, PROOF);
        assertEq(cm.bestProvenResidualKg(claimId), 900);
        assertEq(cm.bestResidualKgOf(buyer, WEEK), 900);
        // a looser cap never replaces a tighter one
        ezk.expect(PROOF, cm.emissionsPublicInputs(claimId, 0, 1000));
        vm.prank(buyer);
        cm.submitEmissionsProof(claimId, 0, 1000, PROOF);
        assertEq(cm.bestProvenResidualKg(claimId), 900);
        // a tighter one does
        ezk.expect(PROOF, cm.emissionsPublicInputs(claimId, 0, 0));
        vm.prank(buyer);
        cm.submitEmissionsProof(claimId, 0, 0, PROOF);
        assertEq(cm.bestProvenResidualKg(claimId), 0);
        assertEq(cm.bestResidualKgOf(buyer, WEEK), 0);
        // the emissions proof does not touch the coverage record
        assertEq(cm.bestProvenBps(buyer, WEEK), 0);
    }

    function test_lowerCapThanProvenRejected() public {
        uint256 claimId = _claim();
        _postIntensity(168);
        ezk.expect(PROOF, cm.emissionsPublicInputs(claimId, 4000, 900));
        vm.startPrank(buyer);
        vm.expectRevert(ClaimManager.ProofRejected.selector);
        cm.submitEmissionsProof(claimId, 4000, 899, PROOF);
        vm.expectRevert(ClaimManager.ProofRejected.selector);
        cm.submitEmissionsProof(claimId, 4001, 900, PROOF);
        vm.stopPrank();
    }

    /// A proof built on a cleaner (fake) intensity vector fails: the contract reads the oracle's values.
    function test_fakeIntensityVectorRejected() public {
        uint256 claimId = _claim();
        _postIntensity(168);
        bytes32[] memory forged = cm.emissionsPublicInputs(claimId, 0, 900);
        forged[170 + 5] = bytes32(uint256(1)); // hour 5 "almost clean"
        ezk.expect(PROOF, forged);
        vm.prank(buyer);
        vm.expectRevert(ClaimManager.ProofRejected.selector);
        cm.submitEmissionsProof(claimId, 0, 900, PROOF);
    }

    function test_fakeCertificatesRejected() public {
        uint256 claimId = _claim();
        _postIntensity(168);
        bytes32[] memory forged = cm.emissionsPublicInputs(claimId, 0, 900);
        forged[2 + 7] = bytes32(uint256(999_000));
        ezk.expect(PROOF, forged);
        vm.prank(buyer);
        vm.expectRevert(ClaimManager.ProofRejected.selector);
        cm.submitEmissionsProof(claimId, 0, 900, PROOF);
    }

    /// The coverage proof's verifier cannot stand in for the emissions verifier (different circuits).
    function test_coverageProofIsNotAnEmissionsProof() public {
        uint256 claimId = _claim();
        _postIntensity(168);
        zk.expect(PROOF, cm.publicInputs(claimId, 7000));
        vm.prank(buyer);
        vm.expectRevert(ClaimManager.ProofRejected.selector);
        cm.submitEmissionsProof(claimId, 7000, 0, PROOF);
    }

    function test_missingIntensityReverts() public {
        uint256 claimId = _claim();
        _postIntensity(167); // the last hour of the week is missing
        vm.prank(buyer);
        vm.expectRevert(abi.encodeWithSelector(IntensityOracle.NotPosted.selector, ZONE, WEEK + 167 * H));
        cm.submitEmissionsProof(claimId, 0, 900, PROOF);
    }

    function test_otherZoneDoesNotCount() public {
        uint256 claimId = _claim();
        _postIntensity(168);
        cm.setIntensityOracle(io, "DK1"); // nothing posted for DK1
        vm.prank(buyer);
        vm.expectRevert(abi.encodeWithSelector(IntensityOracle.NotPosted.selector, bytes32("DK1"), WEEK));
        cm.submitEmissionsProof(claimId, 0, 900, PROOF);
    }

    function test_needsAttestation() public {
        vm.prank(buyer);
        uint256 claimId = cm.openClaim(WEEK);
        _postIntensity(168);
        vm.prank(buyer);
        vm.expectRevert(abi.encodeWithSelector(ClaimManager.NoLoadAttestation.selector, buyer, WEEK));
        cm.submitEmissionsProof(claimId, 0, 900, PROOF);
    }

    function test_onlyBuyerAndBounds() public {
        uint256 claimId = _claim();
        _postIntensity(168);
        vm.prank(ghostBuyer);
        vm.expectRevert(abi.encodeWithSelector(ClaimManager.NotBuyer.selector, claimId));
        cm.submitEmissionsProof(claimId, 0, 900, PROOF);
        vm.prank(buyer);
        vm.expectRevert(abi.encodeWithSelector(ClaimManager.BadThreshold.selector, uint32(10001)));
        cm.submitEmissionsProof(claimId, 10001, 900, PROOF);
        vm.expectRevert(abi.encodeWithSelector(ClaimManager.UnknownClaim.selector, uint256(99)));
        cm.submitEmissionsProof(99, 0, 900, PROOF);
    }

    function test_notConfigured() public {
        ClaimManager bare = new ClaimManager(IZKVerifier(address(zk)));
        bare.setRegistry(address(regA), true);
        bare.setDataHub(hub, true);
        vm.prank(buyer);
        uint256 claimId = bare.openClaim(WEEK);
        vm.prank(hub);
        bare.attestLoad(buyer, WEEK, COMMIT);
        vm.expectRevert(ClaimManager.EmissionsNotConfigured.selector);
        bare.emissionsPublicInputs(claimId, 0, 900);
        vm.prank(buyer);
        vm.expectRevert(ClaimManager.EmissionsNotConfigured.selector);
        bare.submitEmissionsProof(claimId, 0, 900, PROOF);
    }

    function test_onlyAdminConfigures() public {
        vm.startPrank(buyer);
        vm.expectRevert(ClaimManager.NotAdmin.selector);
        cm.setEmissionsVerifier(IZKVerifier(address(0xBAD)));
        vm.expectRevert(ClaimManager.NotAdmin.selector);
        cm.setIntensityOracle(IntensityOracle(address(0xBAD)), ZONE);
        vm.stopPrank();
    }

    /// Any change to the intensity of any hour changes the public inputs (so the proof no longer verifies).
    function testFuzz_anyIntensityChangeBreaksInputs(uint8 hour, uint32 delta) public {
        uint256 claimId = _claim();
        _postIntensity(168);
        uint256 h = bound(hour, 0, 167);
        delta = uint32(bound(delta, 1, 1000));
        bytes32[] memory p = cm.emissionsPublicInputs(claimId, 0, 900);
        ezk.expect(PROOF, p);
        p[170 + h] = bytes32(uint256(p[170 + h]) + delta);
        assertFalse(ezk.verify(PROOF, p));
        vm.prank(buyer);
        cm.submitEmissionsProof(claimId, 0, 900, PROOF); // the honest vector still verifies
        assertEq(cm.bestProvenResidualKg(claimId), 900);
    }
}
