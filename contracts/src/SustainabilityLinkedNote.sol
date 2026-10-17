// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {ClaimManager} from "./ClaimManager.sol";

interface IERC20Min {
    function transfer(address to, uint256 amount) external returns (bool);
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
}

/// @title SustainabilityLinkedNote
/// @notice A one-period sustainability-linked note with one of two KPIs, fixed at deployment:
///           COVERAGE           — HOURLY clean-energy coverage: met by a proof that coverage >= targetBps;
///           RESIDUAL_EMISSIONS — the issuer's unmatched (residual) location-based emissions for the window:
///                                met by a proof that the residual <= targetResidualKg.
///         The KPI is met only by a zero-knowledge proof accepted by ClaimManager, so the issuer never
///         reveals its hourly load to investors. If no proof meeting the target exists by the deadline,
///         the coupon steps up automatically.
contract SustainabilityLinkedNote {
    enum KpiKind {
        COVERAGE,
        RESIDUAL_EMISSIONS
    }

    string public constant name = "HourProof Sustainability-Linked Note (demo)";
    ClaimManager public immutable claims;
    IERC20Min public immutable payToken;
    address public immutable issuer;
    uint64 public immutable windowStart;
    KpiKind public immutable kpiKind;
    uint32 public immutable targetBps; // COVERAGE only (0 otherwise)
    uint64 public immutable targetResidualKg; // RESIDUAL_EMISSIONS only (0 otherwise)
    uint32 public immutable baseCouponBps;
    uint32 public immutable stepUpBps;
    uint64 public immutable deadline;

    uint256 public totalSupply;
    mapping(address => uint256) public balanceOf;
    mapping(address => bool) public couponClaimed;

    bool public settled;
    bool public kpiMet;
    uint32 public couponBps;
    uint256 public couponPool;

    event Subscribed(address indexed investor, uint256 amount);
    event Settled(bool kpiMet, uint32 provenBps, uint32 couponBps);
    event SettledResidual(bool kpiMet, uint64 provenResidualKg, uint32 couponBps);
    event CouponFunded(uint256 amount);
    event CouponClaimed(address indexed holder, uint256 amount);

    error AlreadySettled();
    error NotSettled();
    error TooEarly();
    error NotIssuer();
    error NothingToClaim();
    error Underfunded();
    error TransferFailed();
    error BadTarget();

    constructor(
        ClaimManager claims_,
        IERC20Min payToken_,
        address issuer_,
        uint64 windowStart_,
        KpiKind kpiKind_,
        uint64 target_, // basis points for COVERAGE, kg CO2 for RESIDUAL_EMISSIONS
        uint32 baseCouponBps_,
        uint32 stepUpBps_,
        uint64 deadline_
    ) {
        claims = claims_;
        payToken = payToken_;
        issuer = issuer_;
        windowStart = windowStart_;
        kpiKind = kpiKind_;
        if (kpiKind_ == KpiKind.COVERAGE) {
            if (target_ == 0 || target_ > 10000) revert BadTarget();
            targetBps = uint32(target_);
        } else {
            if (target_ >= claims_.NO_RESIDUAL_PROOF()) revert BadTarget();
            targetResidualKg = target_;
        }
        baseCouponBps = baseCouponBps_;
        stepUpBps = stepUpBps_;
        deadline = deadline_;
    }

    /// @notice Investor pays principal in payToken; principal goes to the issuer; notes are minted 1:1.
    function subscribe(uint256 amount) external {
        if (settled) revert AlreadySettled();
        balanceOf[msg.sender] += amount;
        totalSupply += amount;
        emit Subscribed(msg.sender, amount);
        if (!payToken.transferFrom(msg.sender, issuer, amount)) revert TransferFailed();
    }

    /// @notice Anyone can settle: immediately if the KPI is proven, otherwise after the deadline.
    function settle() external {
        if (settled) revert AlreadySettled();
        bool met;
        uint32 provenBps;
        uint64 provenKg;
        if (kpiKind == KpiKind.COVERAGE) {
            provenBps = claims.bestProvenBps(issuer, windowStart);
            met = provenBps >= targetBps;
        } else {
            provenKg = claims.bestResidualKgOf(issuer, windowStart); // NO_RESIDUAL_PROOF if none
            met = provenKg <= targetResidualKg;
        }
        if (!met && block.timestamp < deadline) revert TooEarly();
        settled = true;
        kpiMet = met;
        couponBps = met ? baseCouponBps : baseCouponBps + stepUpBps;
        if (kpiKind == KpiKind.COVERAGE) emit Settled(met, provenBps, couponBps);
        else emit SettledResidual(met, provenKg, couponBps);
    }

    function couponDue() public view returns (uint256) {
        return totalSupply * couponBps / 10000;
    }

    function fundCoupon() external {
        if (!settled) revert NotSettled();
        if (msg.sender != issuer) revert NotIssuer();
        uint256 due = couponDue() - couponPool;
        couponPool += due;
        emit CouponFunded(due);
        if (!payToken.transferFrom(msg.sender, address(this), due)) revert TransferFailed();
    }

    function claimCoupon() external {
        if (!settled) revert NotSettled();
        if (couponClaimed[msg.sender] || balanceOf[msg.sender] == 0) revert NothingToClaim();
        if (couponPool < couponDue()) revert Underfunded();
        couponClaimed[msg.sender] = true;
        uint256 amt = balanceOf[msg.sender] * couponBps / 10000;
        emit CouponClaimed(msg.sender, amt);
        if (!payToken.transfer(msg.sender, amt)) revert TransferFailed();
    }
}
