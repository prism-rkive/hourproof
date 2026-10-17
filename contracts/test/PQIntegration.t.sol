// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {HourProofBase} from "./Base.t.sol";
import {IMLDSAVerifier} from "mldsa/IMLDSAVerifier.sol";
import {MLDSA44Verifier} from "mldsa/MLDSA44Verifier.sol";
import {CertRegistry} from "../src/CertRegistry.sol";

/// Real post-quantum issuance: FIPS 204 ML-DSA-44 signatures checked on-chain by the
/// vendored Fireblocks verifier (unaudited research code). Signing runs in Python via ffi.
contract PQIntegrationTest is HourProofBase {
    address blob;

    function _deployRuntime(bytes memory runtime) internal returns (address a) {
        bytes memory init = abi.encodePacked(hex"61", uint16(runtime.length), hex"80600a3d393df3", runtime);
        assembly {
            a := create(0, add(init, 0x20), mload(init))
        }
        require(a != address(0) && a.code.length == runtime.length, "runtime deploy failed");
    }

    function _pqVerifier() internal override returns (IMLDSAVerifier) {
        address helper = _deployRuntime(vm.parseBytes(vm.readFile("lib/evm-ml-dsa-verifier/helpers/f1600_170.hex")));
        blob = _deployRuntime(vm.parseBytes(vm.readFile("test/fixtures/pq/issuer_blob.hex")));
        return new MLDSA44Verifier(helper);
    }

    function setUp() public override {
        super.setUp();
        regA.registerIssuer(ISSUER_A, blob);
    }

    function _sign(bytes memory message) internal returns (bytes memory) {
        string[] memory cmd = new string[](4);
        cmd[0] = "python3";
        cmd[1] = "test/ffi/mldsa_sign.py";
        cmd[2] = "test/fixtures/pq/issuer_sk.hex";
        cmd[3] = vm.toString(message);
        return vm.ffi(cmd);
    }

    function test_realMLDSAIssuance() public {
        CertRegistry.CertInput[] memory b = _one(WEEK, 0, 100, buyer);
        bytes memory sig = _sign(regA.batchMessage(ISSUER_A, b));
        assertEq(sig.length, 2420);
        uint256 g = gasleft();
        uint256 id = regA.issueBatch(ISSUER_A, b, sig);
        emit log_named_uint("gas: issueBatch(1 cert) incl. ML-DSA-44 verify", g - gasleft());
        assertEq(id, 1);
    }

    function test_signatureDoesNotTransferToAnotherBatch() public {
        CertRegistry.CertInput[] memory signed = _one(WEEK, 0, 100, buyer);
        bytes memory sig = _sign(regA.batchMessage(ISSUER_A, signed));
        CertRegistry.CertInput[] memory tampered = _one(WEEK, 0, 100, ghostBuyer); // owner swapped
        vm.expectRevert(abi.encodeWithSelector(CertRegistry.BadIssuerSignature.selector, ISSUER_A));
        regA.issueBatch(ISSUER_A, tampered, sig);
    }

    function test_signatureCannotBeReplayed() public {
        CertRegistry.CertInput[] memory b = _one(WEEK, 0, 10, buyer);
        bytes memory sig = _sign(regA.batchMessage(ISSUER_A, b));
        regA.issueBatch(ISSUER_A, b, sig);
        vm.expectRevert(abi.encodeWithSelector(CertRegistry.BadIssuerSignature.selector, ISSUER_A));
        regA.issueBatch(ISSUER_A, b, sig); // nonce moved on
    }

    function test_signatureBoundToRegistry() public {
        regB.registerIssuer(ISSUER_A, blob); // same issuer key accredited at registry B
        CertRegistry.CertInput[] memory b = _one(WEEK, 0, 10, buyer);
        bytes memory sig = _sign(regA.batchMessage(ISSUER_A, b));
        vm.expectRevert(abi.encodeWithSelector(CertRegistry.BadIssuerSignature.selector, ISSUER_A));
        regB.issueBatch(ISSUER_A, b, sig);
    }
}
