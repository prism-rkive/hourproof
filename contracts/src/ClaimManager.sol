// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IZKVerifier} from "./interfaces/IZKVerifier.sol";
import {IntensityOracle} from "./IntensityOracle.sol";

/// @title ClaimManager
/// @notice A buyer's hourly-matching claim for one 168-hour window.
///         1. the buyer opens a claim for a window,
///         2. registries report every certificate the buyer cancels into it (MWh per hour),
///         3. the metering data hub (DSO/TSO data hub) attests a commitment to the buyer's
///            hourly load for that window — the load itself never goes on-chain,
///         4. the buyer submits a zero-knowledge proof that
///               sum_h min(load_h, cert_h) * 10000 >= threshold_bps * sum_h load_h.
///         The contract builds the proof's public inputs ITSELF from on-chain state
///         (threshold, the cancelled certificate vector, the attested load commitment),
///         so a prover cannot substitute different certificates or a different load.
///         5. optionally, a second proof (emissions circuit) over the SAME attested commitment that
///               coverage >= threshold AND sum_h (load_h - min(load_h, cert_h)) * intensity_h <= cap_kg * 1000,
///            with the hourly intensity rebuilt from IntensityOracle (a prover cannot use a cleaner vector).
contract ClaimManager {
    uint256 public constant HOURS = 168;
    uint64 internal constant HOUR = 3600;
    /// @notice bestProvenResidualKg / bestResidualKgOf when no emissions proof was accepted yet. The circuit
    ///         computes cap_kg * 1000 in u64, so this value can never be proven.
    uint64 public constant NO_RESIDUAL_PROOF = type(uint64).max;

    struct Claim {
        address buyer;
        uint64 windowStart;
        uint32 provenBps; // best threshold proven so far (0 = none)
        uint32 cancelledMWh;
    }

    address public immutable admin;
    IZKVerifier public verifier;
    mapping(address => bool) public isRegistry;
    mapping(address => bool) public isDataHub;

    mapping(uint256 => Claim) public claims;
    mapping(uint256 => mapping(uint256 => uint32)) public certMWh; // claimId => hour index => MWh
    mapping(address => mapping(uint64 => bytes32)) public loadCommitment; // buyer => windowStart => commitment
    mapping(address => mapping(uint64 => uint32)) public bestProvenBps; // buyer => windowStart => bps
    uint256 public nextClaimId = 1;

    IZKVerifier public emissionsVerifier;
    IntensityOracle public intensityOracle;
    bytes32 public intensityZone;
    mapping(uint256 => uint128) private _capKgPlusOne; // claimId => best (lowest) proven cap + 1 (0 = none)
    mapping(address => mapping(uint64 => uint128)) private _windowCapKgPlusOne; // buyer => windowStart => same

    event VerifierSet(address verifier);
    event RegistrySet(address indexed registry, bool allowed);
    event DataHubSet(address indexed hub, bool allowed);
    event ClaimOpened(uint256 indexed claimId, address indexed buyer, uint64 windowStart);
    event CancellationRecorded(uint256 indexed claimId, uint256 hourIndex, uint32 mwh);
    event LoadAttested(address indexed buyer, uint64 indexed windowStart, bytes32 commitment, address hub);
    event CoverageProven(uint256 indexed claimId, address indexed buyer, uint64 indexed windowStart, uint32 thresholdBps);
    event EmissionsVerifierSet(address verifier);
    event IntensityOracleSet(address oracle, bytes32 zone);
    event EmissionsProven(
        uint256 indexed claimId, address indexed buyer, uint64 indexed windowStart, uint32 thresholdBps, uint64 capKg
    );

    error NotAdmin();
    error NotRegistry(address caller);
    error NotDataHub(address caller);
    error NotBuyer(uint256 claimId);
    error UnknownClaim(uint256 claimId);
    error NotHourAligned(uint64 t);
    error HourOutsideWindow(uint64 hourStartUtc);
    error AlreadyAttested(address buyer, uint64 windowStart);
    error NoLoadAttestation(address buyer, uint64 windowStart);
    error BadThreshold(uint32 bps);
    error ProofRejected();
    error EmissionsNotConfigured();

    constructor(IZKVerifier verifier_) {
        admin = msg.sender;
        verifier = verifier_;
        emit VerifierSet(address(verifier_));
    }

    modifier onlyAdmin() {
        if (msg.sender != admin) revert NotAdmin();
        _;
    }

    function setVerifier(IZKVerifier v) external onlyAdmin {
        verifier = v;
        emit VerifierSet(address(v));
    }

    function setEmissionsVerifier(IZKVerifier v) external onlyAdmin {
        emissionsVerifier = v;
        emit EmissionsVerifierSet(address(v));
    }

    function setIntensityOracle(IntensityOracle oracle, bytes32 zone) external onlyAdmin {
        intensityOracle = oracle;
        intensityZone = zone;
        emit IntensityOracleSet(address(oracle), zone);
    }

    function setRegistry(address registry, bool allowed) external onlyAdmin {
        isRegistry[registry] = allowed;
        emit RegistrySet(registry, allowed);
    }

    function setDataHub(address hub, bool allowed) external onlyAdmin {
        isDataHub[hub] = allowed;
        emit DataHubSet(hub, allowed);
    }

    function openClaim(uint64 windowStart) external returns (uint256 claimId) {
        if (windowStart % HOUR != 0) revert NotHourAligned(windowStart);
        claimId = nextClaimId++;
        claims[claimId] = Claim(msg.sender, windowStart, 0, 0);
        emit ClaimOpened(claimId, msg.sender, windowStart);
    }

    function recordCancellation(uint256 claimId, address buyer, uint64 hourStartUtc, uint32 mwh) external {
        if (!isRegistry[msg.sender]) revert NotRegistry(msg.sender);
        Claim storage c = claims[claimId];
        if (c.buyer == address(0)) revert UnknownClaim(claimId);
        if (c.buyer != buyer) revert NotBuyer(claimId);
        if (hourStartUtc < c.windowStart || hourStartUtc >= c.windowStart + HOURS * HOUR) {
            revert HourOutsideWindow(hourStartUtc);
        }
        uint256 idx = (hourStartUtc - c.windowStart) / HOUR;
        certMWh[claimId][idx] += mwh;
        c.cancelledMWh += mwh;
        emit CancellationRecorded(claimId, idx, mwh);
    }

    function attestLoad(address buyer, uint64 windowStart, bytes32 commitment) external {
        if (!isDataHub[msg.sender]) revert NotDataHub(msg.sender);
        if (loadCommitment[buyer][windowStart] != bytes32(0)) revert AlreadyAttested(buyer, windowStart);
        loadCommitment[buyer][windowStart] = commitment;
        emit LoadAttested(buyer, windowStart, commitment, msg.sender);
    }

    /// @notice Public inputs exactly as the coverage circuit orders them:
    ///         [threshold_bps, cert_kwh[0..167], load_commitment]
    function publicInputs(uint256 claimId, uint32 thresholdBps) public view returns (bytes32[] memory p) {
        Claim storage c = claims[claimId];
        if (c.buyer == address(0)) revert UnknownClaim(claimId);
        bytes32 commitment = loadCommitment[c.buyer][c.windowStart];
        if (commitment == bytes32(0)) revert NoLoadAttestation(c.buyer, c.windowStart);
        p = new bytes32[](HOURS + 2);
        p[0] = bytes32(uint256(thresholdBps));
        for (uint256 i; i < HOURS; ++i) {
            p[i + 1] = bytes32(uint256(certMWh[claimId][i]) * 1000); // kWh, as in the circuit
        }
        p[HOURS + 1] = commitment;
    }

    function submitProof(uint256 claimId, uint32 thresholdBps, bytes calldata proof) external {
        Claim storage c = claims[claimId];
        if (c.buyer == address(0)) revert UnknownClaim(claimId);
        if (msg.sender != c.buyer) revert NotBuyer(claimId);
        if (thresholdBps == 0 || thresholdBps > 10000) revert BadThreshold(thresholdBps);
        bytes32[] memory p = publicInputs(claimId, thresholdBps);
        bool ok;
        try verifier.verify(proof, p) returns (bool r) {
            ok = r;
        } catch {
            ok = false;
        }
        if (!ok) revert ProofRejected();
        if (thresholdBps > c.provenBps) c.provenBps = thresholdBps;
        if (thresholdBps > bestProvenBps[c.buyer][c.windowStart]) bestProvenBps[c.buyer][c.windowStart] = thresholdBps;
        emit CoverageProven(claimId, c.buyer, c.windowStart, thresholdBps);
    }

    /// @notice Public inputs exactly as the emissions circuit orders them:
    ///         [threshold_bps, cap_kg, cert_kwh[0..167], intensity_g_per_kwh[0..167], load_commitment].
    ///         Certificates come from this contract's records, intensity from IntensityOracle (reverts with
    ///         IntensityOracle.NotPosted if any hour of the window has no posted value), the commitment from
    ///         the data hub's attestation: the same one the coverage proof uses.
    function emissionsPublicInputs(uint256 claimId, uint32 thresholdBps, uint64 capKg)
        public
        view
        returns (bytes32[] memory p)
    {
        Claim storage c = claims[claimId];
        if (c.buyer == address(0)) revert UnknownClaim(claimId);
        if (address(intensityOracle) == address(0)) revert EmissionsNotConfigured();
        bytes32 commitment = loadCommitment[c.buyer][c.windowStart];
        if (commitment == bytes32(0)) revert NoLoadAttestation(c.buyer, c.windowStart);
        uint32[] memory g = intensityOracle.intensities(intensityZone, c.windowStart, HOURS);
        p = new bytes32[](2 * HOURS + 3);
        p[0] = bytes32(uint256(thresholdBps));
        p[1] = bytes32(uint256(capKg));
        for (uint256 i; i < HOURS; ++i) {
            p[i + 2] = bytes32(uint256(certMWh[claimId][i]) * 1000); // kWh, as in the circuit
            p[i + 2 + HOURS] = bytes32(uint256(g[i]));
        }
        p[2 * HOURS + 2] = commitment;
    }

    /// @notice Prove coverage >= thresholdBps AND residual (unmatched) emissions <= capKg for the claim's
    ///         week. thresholdBps may be 0 (residual only). Keeps the lowest cap proven per claim and window.
    function submitEmissionsProof(uint256 claimId, uint32 thresholdBps, uint64 capKg, bytes calldata proof) external {
        Claim storage c = claims[claimId];
        if (c.buyer == address(0)) revert UnknownClaim(claimId);
        if (msg.sender != c.buyer) revert NotBuyer(claimId);
        if (thresholdBps > 10000) revert BadThreshold(thresholdBps);
        if (address(emissionsVerifier) == address(0)) revert EmissionsNotConfigured();
        bytes32[] memory p = emissionsPublicInputs(claimId, thresholdBps, capKg);
        bool ok;
        try emissionsVerifier.verify(proof, p) returns (bool r) {
            ok = r;
        } catch {
            ok = false;
        }
        if (!ok) revert ProofRejected();
        uint128 v = uint128(capKg) + 1;
        uint128 cur = _capKgPlusOne[claimId];
        if (cur == 0 || v < cur) _capKgPlusOne[claimId] = v;
        cur = _windowCapKgPlusOne[c.buyer][c.windowStart];
        if (cur == 0 || v < cur) _windowCapKgPlusOne[c.buyer][c.windowStart] = v;
        emit EmissionsProven(claimId, c.buyer, c.windowStart, thresholdBps, capKg);
    }

    /// @return capKg the lowest residual-emissions cap proven for the claim (NO_RESIDUAL_PROOF if none)
    function bestProvenResidualKg(uint256 claimId) external view returns (uint64) {
        uint128 v = _capKgPlusOne[claimId];
        // forge-lint: disable-next-line(unsafe-typecast)
        return v == 0 ? NO_RESIDUAL_PROOF : uint64(v - 1); // v = capKg + 1 <= 2^64
    }

    /// @return capKg the lowest cap proven by any of the buyer's claims for that window (NO_RESIDUAL_PROOF if none)
    function bestResidualKgOf(address buyer, uint64 windowStart) external view returns (uint64) {
        uint128 v = _windowCapKgPlusOne[buyer][windowStart];
        // forge-lint: disable-next-line(unsafe-typecast)
        return v == 0 ? NO_RESIDUAL_PROOF : uint64(v - 1); // v = capKg + 1 <= 2^64
    }

    function certVector(uint256 claimId) external view returns (uint32[] memory v) {
        v = new uint32[](HOURS);
        for (uint256 i; i < HOURS; ++i) v[i] = certMWh[claimId][i];
    }
}
