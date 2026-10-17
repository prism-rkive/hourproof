// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IMLDSAVerifier} from "mldsa/IMLDSAVerifier.sol";
import {HourKey} from "./libraries/HourKey.sol";
import {SliceLedger} from "./SliceLedger.sol";
import {ProductionOracle} from "./ProductionOracle.sol";

interface IClaimSink {
    function recordCancellation(uint256 claimId, address buyer, uint64 hourStartUtc, uint32 mwh) external;
}

/// @title CertRegistry
/// @notice An hourly energy-attribute-certificate registry. Several independent registries can
///         exist; all of them cancel through the one shared SliceLedger.
///         Issuance is authorised by a post-quantum (ML-DSA-44, FIPS 204) signature from an
///         accredited issuer over the whole batch, and is capped by metered production.
contract CertRegistry {
    struct CertInput {
        bytes32 zone;
        bytes32 asset;
        uint64 hourStartUtc;
        uint32 first; // first MWh slice of the hour
        uint32 count; // MWh
        address owner;
    }

    struct Cert {
        bytes32 key;
        uint64 hourStartUtc;
        uint32 first;
        uint32 count;
        address owner;
        bool cancelled;
    }

    struct Issuer {
        address pkBlob; // ML-DSA-44 prepared public key (data contract)
        bool active;
        uint64 nonce;
    }

    string public name;
    address public immutable operator;
    SliceLedger public immutable ledger;
    ProductionOracle public immutable oracle;
    IMLDSAVerifier public immutable pqVerifier;
    IClaimSink public claimSink;

    mapping(bytes32 => Issuer) public issuers;
    mapping(uint256 => Cert) public certs;
    uint256 public nextId = 1;

    event IssuerRegistered(bytes32 indexed issuerId, address pkBlob);
    event IssuerActive(bytes32 indexed issuerId, bool active);
    event BatchIssued(bytes32 indexed issuerId, uint64 nonce, uint256 firstId, uint256 count, bytes32 batchHash);
    event Issued(uint256 indexed id, bytes32 indexed key, uint64 hourStartUtc, uint32 first, uint32 count, address owner);
    event Transferred(uint256 indexed id, address from, address to);
    event Cancelled(uint256 indexed id, address indexed owner, uint256 indexed claimId, bytes32 claimRef);

    error NotOperator();
    error UnknownIssuer(bytes32 issuerId);
    error BadIssuerSignature(bytes32 issuerId);
    error EmptyBatch();
    error ZeroCount();
    error ExceedsProduction(bytes32 key, uint256 lastSlice, uint32 produced);
    error NotOwner(uint256 id);
    error AlreadyCancelled(uint256 id);

    constructor(string memory name_, SliceLedger ledger_, ProductionOracle oracle_, IMLDSAVerifier pqVerifier_) {
        name = name_;
        operator = msg.sender;
        ledger = ledger_;
        oracle = oracle_;
        pqVerifier = pqVerifier_;
    }

    modifier onlyOperator() {
        if (msg.sender != operator) revert NotOperator();
        _;
    }

    function setClaimSink(IClaimSink sink) external onlyOperator {
        claimSink = sink;
    }

    function registerIssuer(bytes32 issuerId, address pkBlob) external onlyOperator {
        issuers[issuerId] = Issuer(pkBlob, true, 0);
        emit IssuerRegistered(issuerId, pkBlob);
    }

    function setIssuerActive(bytes32 issuerId, bool active) external onlyOperator {
        issuers[issuerId].active = active;
        emit IssuerActive(issuerId, active);
    }

    /// @notice Exact bytes the issuer must sign (ML-DSA-44, empty context) for its next batch.
    function batchMessage(bytes32 issuerId, CertInput[] calldata batch) public view returns (bytes memory) {
        return abi.encodePacked(
            "HOURPROOF/v1/issue", block.chainid, address(this), issuerId, issuers[issuerId].nonce, keccak256(abi.encode(batch))
        );
    }

    function issueBatch(bytes32 issuerId, CertInput[] calldata batch, bytes calldata signature)
        external
        returns (uint256 firstId)
    {
        Issuer storage iss = issuers[issuerId];
        if (!iss.active || iss.pkBlob == address(0)) revert UnknownIssuer(issuerId);
        if (batch.length == 0) revert EmptyBatch();
        if (!pqVerifier.verify(iss.pkBlob, batchMessage(issuerId, batch), signature)) {
            revert BadIssuerSignature(issuerId);
        }
        uint64 nonce = iss.nonce++;
        firstId = nextId;
        for (uint256 i; i < batch.length; ++i) {
            CertInput calldata c = batch[i];
            if (c.count == 0) revert ZeroCount();
            bytes32 key = HourKey.compute(c.zone, c.hourStartUtc, c.asset);
            uint32 produced = oracle.productionOf(key);
            if (uint256(c.first) + c.count > produced) revert ExceedsProduction(key, uint256(c.first) + c.count, produced);
            uint256 id = nextId++;
            certs[id] = Cert(key, c.hourStartUtc, c.first, c.count, c.owner, false);
            emit Issued(id, key, c.hourStartUtc, c.first, c.count, c.owner);
        }
        emit BatchIssued(issuerId, nonce, firstId, batch.length, keccak256(abi.encode(batch)));
    }

    function transfer(uint256 id, address to) external {
        Cert storage c = certs[id];
        if (c.owner != msg.sender) revert NotOwner(id);
        if (c.cancelled) revert AlreadyCancelled(id);
        c.owner = to;
        emit Transferred(id, msg.sender, to);
    }

    /// @notice Cancel (retire) certificates for a claim. claimId = 0 cancels without a ClaimManager claim.
    function cancelBatch(uint256[] calldata ids, uint256 claimId, bytes32 claimRef) external {
        for (uint256 i; i < ids.length; ++i) {
            Cert storage c = certs[ids[i]];
            if (c.owner != msg.sender) revert NotOwner(ids[i]);
            if (c.cancelled) revert AlreadyCancelled(ids[i]);
            c.cancelled = true;
            ledger.spend(c.key, c.first, c.count, claimRef);
            if (claimId != 0) claimSink.recordCancellation(claimId, msg.sender, c.hourStartUtc, c.count);
            emit Cancelled(ids[i], msg.sender, claimId, claimRef);
        }
    }
}
