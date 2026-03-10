from __future__ import annotations

import json

import pytest

from pyglaze.device import (
    CatalogSelectionStatus,
    parse_release_manifest,
    select_release_for_device_info,
    select_release_for_target,
)
from pyglaze.mimlink.proto.envelope_pb2 import TRANSFER_MODE_BULK
from pyglaze.scanning import DeviceInfo


def _manifest_dict() -> dict[str, object]:
    return {
        "schema_version": 1,
        "product": "mimos",
        "release_version": "1.0.0",
        "channel": "stable",
        "published_at": "2026-03-08T11:00:00Z",
        "targets": [
            {
                "firmware_target": "le23-r1",
                "display_name": "Le 2.3.0",
                "artifact_name": "mimos-le23-r1-v1.0.0.signed.bin",
                "artifact_url": "https://example.invalid/le23.bin",
                "sha256": "a" * 64,
                "size_bytes": 262144,
                "format": "mcuboot-signed-bin",
                "support_status": "legacy",
                "product_models": ["Carmen"],
                "release_profile": "stable",
                "feature_flags": {"mimlink_transfer_mode": "bulk"},
                "minimum_consumer_versions": {"pyglaze": "0.6.0"},
            },
            {
                "firmware_target": "le30-r1",
                "display_name": "Le 3.0.0",
                "artifact_name": "mimos-le30-r1-v1.0.0.signed.bin",
                "artifact_url": "https://example.invalid/le30.bin",
                "sha256": "b" * 64,
                "size_bytes": 278528,
                "format": "mcuboot-signed-bin",
                "support_status": "active",
                "minimum_consumer_versions": {
                    "pyglaze": "0.6.0",
                    "glaze-desktop": "1.2.0",
                },
            },
        ],
    }


def test_parse_release_manifest_from_string() -> None:
    manifest = parse_release_manifest(json.dumps(_manifest_dict()))

    assert manifest.release_version == "1.0.0"
    assert manifest.channel == "stable"
    assert len(manifest.targets) == 2
    assert manifest.targets[0].artifact_format == "mcuboot-signed-bin"
    assert manifest.targets[0].product_models == ("Carmen",)
    assert manifest.targets[0].feature_flags["mimlink_transfer_mode"] == "bulk"


def test_parse_release_manifest_from_bytes() -> None:
    manifest = parse_release_manifest(json.dumps(_manifest_dict()).encode("utf-8"))

    assert manifest.targets[1].firmware_target == "le30-r1"


def test_parse_release_manifest_rejects_duplicate_targets() -> None:
    payload = _manifest_dict()
    duplicate_target = dict(payload["targets"][0])  # type: ignore[index]
    payload["targets"] = [duplicate_target, duplicate_target]

    with pytest.raises(ValueError, match="duplicate firmware_target"):
        parse_release_manifest(payload)


def test_parse_release_manifest_rejects_invalid_schema_version() -> None:
    payload = _manifest_dict()
    payload["schema_version"] = 2

    with pytest.raises(ValueError, match="schema_version"):
        parse_release_manifest(payload)


def test_parse_release_manifest_rejects_invalid_product() -> None:
    payload = _manifest_dict()
    payload["product"] = "not-mimos"

    with pytest.raises(ValueError, match="product"):
        parse_release_manifest(payload)


def test_parse_release_manifest_rejects_invalid_channel() -> None:
    payload = _manifest_dict()
    payload["channel"] = "beta"

    with pytest.raises(ValueError, match="channel"):
        parse_release_manifest(payload)


def test_parse_release_manifest_rejects_invalid_format() -> None:
    payload = _manifest_dict()
    payload["targets"][0]["format"] = "zip"  # type: ignore[index]

    with pytest.raises(ValueError, match="format"):
        parse_release_manifest(payload)


def test_parse_release_manifest_rejects_missing_required_target_field() -> None:
    payload = _manifest_dict()
    del payload["targets"][0]["artifact_url"]  # type: ignore[index]

    with pytest.raises(ValueError, match="artifact_url"):
        parse_release_manifest(payload)


def test_select_release_for_target_exact_match() -> None:
    result = select_release_for_target(_manifest_dict(), "le23-r1")

    assert result.status is CatalogSelectionStatus.SELECTED
    assert result.target is not None
    assert result.target.firmware_target == "le23-r1"
    assert result.warning_legacy_support is True


def test_select_release_for_target_returns_no_compatible_release() -> None:
    result = select_release_for_target(_manifest_dict(), "unknown-target")

    assert result.status is CatalogSelectionStatus.NO_COMPATIBLE_RELEASE
    assert result.target is None


def test_select_release_for_target_returns_non_release_managed_target() -> None:
    result = select_release_for_target(_manifest_dict(), "dev-nucleo-f446re")

    assert result.status is CatalogSelectionStatus.NON_RELEASE_MANAGED_TARGET
    assert result.target is None


def test_select_release_for_target_reports_unmet_pyglaze_version() -> None:
    payload = _manifest_dict()
    payload["targets"][0]["minimum_consumer_versions"] = {"pyglaze": "9.9.9"}  # type: ignore[index]

    result = select_release_for_target(payload, "le23-r1")

    assert result.status is CatalogSelectionStatus.CONSUMER_UPGRADE_REQUIRED
    assert result.unmet_consumers["pyglaze"] == "9.9.9"


def test_select_release_for_target_ignores_non_pyglaze_consumer_requirements() -> None:
    result = select_release_for_target(_manifest_dict(), "le30-r1")

    assert result.status is CatalogSelectionStatus.SELECTED
    assert result.target is not None
    assert result.target.firmware_target == "le30-r1"
    assert dict(result.unmet_consumers) == {}


def test_select_release_for_device_info_accepts_scanner_device_info() -> None:
    device_info = DeviceInfo(
        serial_number="M-1234",
        firmware_version="v0.6.0",
        firmware_target="le23-r1",
        bsp_name="le23",
        build_type="Release",
        transfer_mode=TRANSFER_MODE_BULK,
        hardware_type="carmen",
        hardware_revision=1,
    )

    result = select_release_for_device_info(_manifest_dict(), device_info)

    assert result.status is CatalogSelectionStatus.SELECTED
    assert result.target is not None
    assert result.target.firmware_target == "le23-r1"
