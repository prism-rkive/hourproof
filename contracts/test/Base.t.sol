// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {IMLDSAVerifier} from "mldsa/IMLDSAVerifier.sol";
import {SliceLedger} from "../src/SliceLedger.sol";
import {ProductionOracle} from "../src/ProductionOracle.sol";
import {CertRegistry, IClaimSink} from "../src/CertRegistry.sol";
import {ClaimManager} from "../src/ClaimManager.sol";
import {IZKVerifier} from "../src/interfaces/IZKVerifier.sol";
import {MockPQVerifier, MockZKVerifier} from "./mocks/Mocks.sol";

/// @dev Shared fixture: one oracle, one ledger, two independent registries, one claim manager.
abstract contract HourProofBase is Test {
    SliceLedger ledger;
    ProductionOracle oracle;
    CertRegistry regA;
    CertRegistry regB;
    ClaimManager cm;
    MockZKVerifier zk;
    IMLDSAVerifier pq;

    address poster = makeAddr("poster");
    address hub = makeAddr("datahub");
    address buyer = makeAddr("buyer");
    address ghostBuyer = makeAddr("ghostBuyer");
    bytes32 constant ISSUER_A = "issuer-A";
    bytes32 constant ISSUER_B = "issuer-B";
    bytes32 constant ZONE = "DK";
    bytes32 constant ASSET = "DK-wind-declared";
    uint64 constant WEEK = 1736121600; // 2025-01-06T00:00:00Z
    uint64 constant H = 3600;

    function setUp() public virtual {
        ledger = new SliceLedger();
        oracle = new ProductionOracle();
        pq = _pqVerifier();
        regA = new CertRegistry("Registry A", ledger, oracle, pq);
        regB = new CertRegistry("Registry B", ledger, oracle, pq);
        zk = new MockZKVerifier();
        cm = new ClaimManager(IZKVerifier(address(zk)));
        ledger.setRegistry(address(regA), true);
        ledger.setRegistry(address(regB), true);
        cm.setRegistry(address(regA), true);
        cm.setRegistry(address(regB), true);
        cm.setDataHub(hub, true);
        regA.setClaimSink(IClaimSink(address(cm)));
        regB.setClaimSink(IClaimSink(address(cm)));
        oracle.setPoster(poster, true);
        regA.registerIssuer(ISSUER_A, address(0xA11CE)); // pk blob unused by the mock verifier
        regB.registerIssuer(ISSUER_B, address(0xB0B));
        _postWeek(1000);
    }

    function _pqVerifier() internal virtual returns (IMLDSAVerifier) {
        return new MockPQVerifier();
    }

    function _postWeek(uint32 mwh) internal {
        uint64[] memory hrs = new uint64[](168);
        uint32[] memory v = new uint32[](168);
        for (uint256 i; i < 168; ++i) {
            hrs[i] = WEEK + uint64(i) * H;
            v[i] = mwh;
        }
        vm.prank(poster);
        oracle.post(ZONE, ASSET, hrs, v);
    }

    function _one(uint64 hour, uint32 first, uint32 count, address owner)
        internal
        pure
        returns (CertRegistry.CertInput[] memory b)
    {
        b = new CertRegistry.CertInput[](1);
        b[0] = CertRegistry.CertInput(ZONE, ASSET, hour, first, count, owner);
    }

    function _ids(uint256 a) internal pure returns (uint256[] memory x) {
        x = new uint256[](1);
        x[0] = a;
    }
}
