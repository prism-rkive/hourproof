// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IMLDSAVerifier} from "mldsa/IMLDSAVerifier.sol";
import {IZKVerifier} from "../../src/interfaces/IZKVerifier.sol";

/// @dev Accepts any signature except the 1-byte signature 0x00 (used to simulate a forgery).
///      Real ML-DSA verification is covered separately in PQIntegration.t.sol.
contract MockPQVerifier is IMLDSAVerifier {
    function verify(address, bytes calldata, bytes calldata signature) external pure returns (bool) {
        return !(signature.length == 1 && signature[0] == 0x00);
    }
}

/// @dev Accepts exactly one (proof, publicInputs) pair, so tests can check that ClaimManager
///      builds the public inputs correctly. Real UltraHonk verification: HonkIntegration.t.sol.
contract MockZKVerifier is IZKVerifier {
    bytes32 public proofHash;
    bytes32 public pubHash;

    function expect(bytes calldata proof, bytes32[] calldata pub) external {
        proofHash = keccak256(proof);
        pubHash = keccak256(abi.encode(pub));
    }

    function verify(bytes calldata proof, bytes32[] calldata pub) external view returns (bool) {
        return keccak256(proof) == proofHash && keccak256(abi.encode(pub)) == pubHash;
    }
}
