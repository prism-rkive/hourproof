// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {IntensityOracle} from "../src/IntensityOracle.sol";

contract IntensityOracleTest is Test {
    IntensityOracle io;
    address oracle = makeAddr("intensityOracle");
    bytes32 constant ZONE = "DK";
    uint64 constant WEEK = 1736121600; // 2025-01-06T00:00:00Z
    uint64 constant H = 3600;

    function setUp() public {
        io = new IntensityOracle();
        io.setOracle(oracle, true);
    }

    function _one(uint64 h, uint32 g) internal pure returns (uint64[] memory hrs, uint32[] memory v) {
        hrs = new uint64[](1);
        v = new uint32[](1);
        hrs[0] = h;
        v[0] = g;
    }

    function _postWeek(uint64 start, uint32 g) internal {
        uint64[] memory hrs = new uint64[](168);
        uint32[] memory v = new uint32[](168);
        for (uint256 i; i < 168; ++i) {
            hrs[i] = start + uint64(i) * H;
            v[i] = g + uint32(i);
        }
        vm.prank(oracle);
        io.post(ZONE, hrs, v);
    }

    function test_postAndRead() public {
        (uint64[] memory hrs, uint32[] memory v) = _one(WEEK, 123);
        vm.prank(oracle);
        io.post(ZONE, hrs, v);
        assertTrue(io.isPosted(ZONE, WEEK));
        assertEq(io.intensityOf(ZONE, WEEK), 123);
        assertFalse(io.isPosted("DK1", WEEK)); // zones are separate
    }

    function test_zeroIntensityIsAValue() public {
        (uint64[] memory hrs, uint32[] memory v) = _one(WEEK, 0);
        vm.prank(oracle);
        io.post(ZONE, hrs, v);
        assertTrue(io.isPosted(ZONE, WEEK));
        assertEq(io.intensityOf(ZONE, WEEK), 0);
    }

    function test_writeOnce() public {
        (uint64[] memory hrs, uint32[] memory v) = _one(WEEK, 200);
        vm.startPrank(oracle);
        io.post(ZONE, hrs, v);
        v[0] = 100; // a "cleaner" re-post of the same hour
        vm.expectRevert(abi.encodeWithSelector(IntensityOracle.AlreadyPosted.selector, ZONE, WEEK));
        io.post(ZONE, hrs, v);
        vm.stopPrank();
        assertEq(io.intensityOf(ZONE, WEEK), 200);
    }

    function test_duplicateHourInOneBatchReverts() public {
        uint64[] memory hrs = new uint64[](2);
        uint32[] memory v = new uint32[](2);
        hrs[0] = WEEK;
        hrs[1] = WEEK;
        v[0] = 200;
        v[1] = 50;
        vm.prank(oracle);
        vm.expectRevert(abi.encodeWithSelector(IntensityOracle.AlreadyPosted.selector, ZONE, WEEK));
        io.post(ZONE, hrs, v);
    }

    function test_onlyOracle() public {
        (uint64[] memory hrs, uint32[] memory v) = _one(WEEK, 200);
        vm.expectRevert(abi.encodeWithSelector(IntensityOracle.NotOracle.selector, address(this)));
        io.post(ZONE, hrs, v);
        vm.prank(oracle);
        io.post(ZONE, hrs, v);
        io.setOracle(oracle, false);
        (hrs, v) = _one(WEEK + H, 200);
        vm.prank(oracle);
        vm.expectRevert(abi.encodeWithSelector(IntensityOracle.NotOracle.selector, oracle));
        io.post(ZONE, hrs, v);
    }

    function test_onlyAdminSetsOracle() public {
        vm.prank(oracle);
        vm.expectRevert(IntensityOracle.NotAdmin.selector);
        io.setOracle(oracle, true);
    }

    function test_boundedIntensity() public {
        (uint64[] memory hrs, uint32[] memory v) = _one(WEEK, 2000);
        vm.prank(oracle);
        io.post(ZONE, hrs, v); // the bound itself is allowed
        (hrs, v) = _one(WEEK + H, 2001);
        vm.prank(oracle);
        vm.expectRevert(abi.encodeWithSelector(IntensityOracle.IntensityOutOfRange.selector, WEEK + H, uint32(2001)));
        io.post(ZONE, hrs, v);
    }

    function test_hourAligned() public {
        (uint64[] memory hrs, uint32[] memory v) = _one(WEEK + 1, 100);
        vm.prank(oracle);
        vm.expectRevert(abi.encodeWithSelector(IntensityOracle.NotHourAligned.selector, WEEK + 1));
        io.post(ZONE, hrs, v);
    }

    function test_lengthMismatch() public {
        uint64[] memory hrs = new uint64[](2);
        uint32[] memory v = new uint32[](1);
        vm.prank(oracle);
        vm.expectRevert(IntensityOracle.LengthMismatch.selector);
        io.post(ZONE, hrs, v);
    }

    function test_missingHourReverts() public {
        vm.expectRevert(abi.encodeWithSelector(IntensityOracle.NotPosted.selector, ZONE, WEEK));
        io.intensityOf(ZONE, WEEK);
    }

    function test_weekWindow() public {
        _postWeek(WEEK, 100);
        uint32[] memory w = io.intensities(ZONE, WEEK, 168);
        assertEq(w.length, 168);
        assertEq(w[0], 100);
        assertEq(w[167], 267);
        // one hour beyond what was posted
        vm.expectRevert(abi.encodeWithSelector(IntensityOracle.NotPosted.selector, ZONE, WEEK + 168 * H));
        io.intensities(ZONE, WEEK + H, 168);
    }

    // ------------------------------------------------------------------ fuzz
    function testFuzz_roundTripAndWriteOnce(uint64 hourIdx, uint32 g, uint32 g2) public {
        uint64 h = uint64(bound(hourIdx, 0, type(uint64).max / H - 1)) * H;
        g = uint32(bound(g, 0, 2000));
        g2 = uint32(bound(g2, 0, 2000));
        (uint64[] memory hrs, uint32[] memory v) = _one(h, g);
        vm.prank(oracle);
        io.post(ZONE, hrs, v);
        assertEq(io.intensityOf(ZONE, h), g);
        v[0] = g2;
        vm.prank(oracle);
        vm.expectRevert(abi.encodeWithSelector(IntensityOracle.AlreadyPosted.selector, ZONE, h));
        io.post(ZONE, hrs, v);
        assertEq(io.intensityOf(ZONE, h), g);
    }

    function testFuzz_outOfRangeRejected(uint32 g) public {
        g = uint32(bound(g, 2001, type(uint32).max));
        (uint64[] memory hrs, uint32[] memory v) = _one(WEEK, g);
        vm.prank(oracle);
        vm.expectRevert(abi.encodeWithSelector(IntensityOracle.IntensityOutOfRange.selector, WEEK, g));
        io.post(ZONE, hrs, v);
        assertFalse(io.isPosted(ZONE, WEEK));
    }

    function testFuzz_unalignedRejected(uint64 t) public {
        vm.assume(t % H != 0);
        (uint64[] memory hrs, uint32[] memory v) = _one(t, 100);
        vm.prank(oracle);
        vm.expectRevert(abi.encodeWithSelector(IntensityOracle.NotHourAligned.selector, t));
        io.post(ZONE, hrs, v);
    }

    function testFuzz_strangerCannotPost(address who) public {
        vm.assume(who != oracle);
        (uint64[] memory hrs, uint32[] memory v) = _one(WEEK, 100);
        vm.prank(who);
        vm.expectRevert(abi.encodeWithSelector(IntensityOracle.NotOracle.selector, who));
        io.post(ZONE, hrs, v);
    }
}
