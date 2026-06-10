# tests/test_sim_device.py — unit coverage for the sim-device topic contract (no broker)
# @author  Ritesh Anand
# @company embediq.com | ritzylab.com
# SPDX-License-Identifier: Apache-2.0
"""Pure-function tests for the simulated device's topic builders.

These run in the normal unit suite (no broker, no Docker) and pin the device <-> cloud topic
contract from ARCHITECTURE.md, so a typo in the e2e helper fails fast here instead of in CI.
"""

from tests.integration import sim_device


def test_device_to_cloud_topics() -> None:
    assert sim_device.telemetry_topic("d1") == "embediq/d1/telemetry"
    assert sim_device.status_topic("d1") == "embediq/d1/status"
    assert sim_device.reported_topic("d1") == "embediq/d1/state/reported"


def test_cloud_to_device_topics() -> None:
    assert sim_device.desired_topic("d1") == "embediq/d1/state/desired"
    assert sim_device.cmd_topic("d1") == "embediq/d1/cmd"
