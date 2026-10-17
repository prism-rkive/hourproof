// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {HourProofBase} from "./Base.t.sol";
import {ClaimManager} from "../src/ClaimManager.sol";
import {CertRegistry} from "../src/CertRegistry.sol";
import {IntensityOracle} from "../src/IntensityOracle.sol";
import {IZKVerifier} from "../src/interfaces/IZKVerifier.sol";

/// End-to-end with the REAL UltraHonk emissions verifier and a REAL proof over real Danish data
/// (the carbon kill test's K4 week: load, wind and the hourly grid intensity from Energinet).
/// Needs `make zk` and `make fixture` (src/generated/EmissionsHonkVerifier.sol and
/// test/fixtures/zk/emissions_fixture.json). Skipped (not failed) when the fixture is absent.
contract EmissionsIntegrationTest is HourProofBase {
    string constant FIXTURE = "test/fixtures/zk/emissions_fixture.json";
    IZKVerifier honk;
    IntensityOracle io;
    address intensityPoster = makeAddr("intensityPoster");
    uint64 window;
    uint32 threshold;
    uint64 capKg;
    bytes proof;
    bytes32 commitment;
    uint256 claimId;
    uint256[] g;

    function setUp() public override {
        super.setUp();
        if (!vm.exists(FIXTURE)) return;
        honk = IZKVerifier(deployCode("EmissionsHonkVerifier.sol:EmissionsHonkVerifier"));
        io = new IntensityOracle();
        io.setOracle(intensityPoster, true);
        cm.setEmissionsVerifier(honk);
        cm.setIntensityOracle(io, ZONE);
        string memory j = vm.readFile(FIXTURE);
        window = uint64(vm.parseJsonUint(j, ".window_start"));
        threshold = uint32(vm.parseJsonUint(j, ".threshold_bps"));
        capKg = uint64(vm.parseJsonUint(j, ".cap_kg"));
        proof = vm.parseJsonBytes(j, ".proof");
        commitment = vm.parseJsonBytes32(j, ".load_commitment");
        uint256[] memory certs = vm.parseJsonUintArray(j, ".cert_mwh");
        g = vm.parseJsonUintArray(j, ".intensity_g_per_kwh");
        require(certs.length == 168 && g.length == 168, "fixture: need 168 hours");

        uint64[] memory hrs = new uint64[](168);
        uint32[] memory v = new uint32[](168);
        uint32[] memory gi = new uint32[](168);
        for (uint256 i; i < 168; ++i) {
            hrs[i] = window + uint64(i) * H;
            v[i] = uint32(certs[i] + 1);
            gi[i] = uint32(g[i]);
        }
        vm.prank(poster);
        oracle.post(ZONE, ASSET, hrs, v);
        vm.prank(intensityPoster);
        io.post(ZONE, hrs, gi);

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
        regA.cancelBatch(ids, claimId, "zk-emissions-fixture");
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

    function test_realEmissionsProofAccepted() public needsFixture {
        vm.prank(buyer);
        uint256 gas0 = gasleft();
        cm.submitEmissionsProof(claimId, threshold, capKg, proof);
        emit log_named_uint("gas: submitEmissionsProof incl. UltraHonk verify (339 public inputs)", gas0 - gasleft());
        assertEq(cm.bestProvenResidualKg(claimId), capKg);
        assertEq(cm.bestResidualKgOf(buyer, window), capKg);
    }

    function test_realProofCannotClaimLowerCap() public needsFixture {
        vm.prank(buyer);
        vm.expectRevert(ClaimManager.ProofRejected.selector);
        cm.submitEmissionsProof(claimId, threshold, capKg - 1, proof);
    }

    function test_realProofCannotClaimHigherCoverage() public needsFixture {
        vm.prank(buyer);
        vm.expectRevert(ClaimManager.ProofRejected.selector);
        cm.submitEmissionsProof(claimId, threshold + 1, capKg, proof);
    }

    /// The proof was made on the true intensities. Against an oracle that posted one hour 1 g/kWh lower
    /// (or any other vector) it fails: the contract, not the prover, decides which intensities are public.
    function test_realProofBoundToOracleIntensity() public needsFixture {
        IntensityOracle other = new IntensityOracle();
        other.setOracle(intensityPoster, true);
        uint64[] memory hrs = new uint64[](168);
        uint32[] memory gi = new uint32[](168);
        for (uint256 i; i < 168; ++i) {
            hrs[i] = window + uint64(i) * H;
            gi[i] = uint32(g[i]);
        }
        gi[100] = gi[100] > 0 ? gi[100] - 1 : 1;
        vm.prank(intensityPoster);
        other.post(ZONE, hrs, gi);
        cm.setIntensityOracle(other, ZONE);
        vm.prank(buyer);
        vm.expectRevert(ClaimManager.ProofRejected.selector);
        cm.submitEmissionsProof(claimId, threshold, capKg, proof);
    }

    /// The coverage verifier does not accept an emissions proof (different circuit, different key).
    function test_emissionsProofIsNotACoverageProof() public needsFixture {
        cm.setVerifier(IZKVerifier(deployCode("HonkVerifier.sol:HonkVerifier")));
        vm.prank(buyer);
        vm.expectRevert(ClaimManager.ProofRejected.selector);
        cm.submitProof(claimId, threshold, proof);
    }

    function test_realProofNotTransferableToAnotherClaim() public needsFixture {
        vm.prank(hub);
        cm.attestLoad(ghostBuyer, window, bytes32(uint256(12345)));
        vm.prank(ghostBuyer);
        uint256 other = cm.openClaim(window);
        vm.prank(ghostBuyer);
        vm.expectRevert(ClaimManager.ProofRejected.selector);
        cm.submitEmissionsProof(other, threshold, capKg, proof);
    }
}
