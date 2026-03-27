from __future__ import annotations

import json
from types import SimpleNamespace
from typing import cast

import pytest

from pyglaze.device import (
    CatalogSelectionStatus,
    parse_release_manifest,
    select_release_for_device_info,
    select_release_for_target,
)


def _manifest_dict() -> dict[str, object]:
    return {
        "schema_version": 1,
        "product": "mimos",
        "release_version": "1.0.0",
        "channel": "stable",
        "published_at": "2026-03-08T11:00:00Z",
        "targets": [
            {
                "firmware_target": "le-2-3-0",
                "display_name": "Le 2.3.0",
                "artifact_name": "mimos-le-2-3-0-v1.0.0.signed.bin",
                "artifact_url": "https://example.invalid/le23.bin",
                "sha256": "a" * 64,
                "size_bytes": 262144,
                "format": "mcuboot-signed-bin",
                "support_status": "legacy",
                "release_profile": "stable",
                "minimum_consumer_versions": {"pyglaze": "0.6.0"},
            },
            {
                "firmware_target": "le-3-0-0",
                "display_name": "Le 3.0.0",
                "artifact_name": "mimos-le-3-0-0-v1.0.0.signed.bin",
                "artifact_url": "https://example.invalid/le30.bin",
                "sha256": "b" * 64,
                "size_bytes": 278528,
                "format": "mcuboot-signed-bin",
                "support_status": "active",
            },
        ],
    }


def _first_target(payload: dict[str, object]) -> dict[str, object]:
    return cast("list[dict[str, object]]", payload["targets"])[0]


def test_parse_release_manifest_from_string() -> None:
    manifest = parse_release_manifest(json.dumps(_manifest_dict()))

    assert manifest.release_version == "1.0.0"
    assert manifest.channel == "stable"
    assert len(manifest.targets) == 2
    assert manifest.targets[0].artifact_format == "mcuboot-signed-bin"
    assert manifest.targets[0].support_status == "legacy"
    assert manifest.targets[0].release_profile == "stable"


def test_parse_release_manifest_passes_through_already_parsed() -> None:
    manifest = parse_release_manifest(_manifest_dict())
    assert parse_release_manifest(manifest) is manifest


def test_parse_release_manifest_rejects_blank_required_strings() -> None:
    payload = _manifest_dict()
    _first_target(payload)["artifact_url"] = "   "

    with pytest.raises(ValueError, match="artifact_url"):
        parse_release_manifest(payload)


def test_parse_release_manifest_rejects_invalid_json() -> None:
    with pytest.raises(ValueError, match="valid JSON"):
        parse_release_manifest("{")


def test_parse_release_manifest_rejects_non_object_root() -> None:
    with pytest.raises(TypeError, match="manifest root"):
        parse_release_manifest("[]")


def test_parse_release_manifest_rejects_duplicate_targets() -> None:
    payload = _manifest_dict()
    duplicate_target = dict(_first_target(payload))
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


def test_parse_release_manifest_rejects_targets_that_are_not_lists() -> None:
    payload = _manifest_dict()
    payload["targets"] = "not-a-list"

    with pytest.raises(TypeError, match="targets must be a list"):
        parse_release_manifest(payload)


def test_parse_release_manifest_rejects_non_object_target_entries() -> None:
    payload = _manifest_dict()
    payload["targets"] = ["not-an-object"]

    with pytest.raises(TypeError, match="target entries must be objects"):
        parse_release_manifest(payload)


def test_parse_release_manifest_rejects_missing_required_target_field() -> None:
    payload = _manifest_dict()
    del _first_target(payload)["artifact_url"]

    with pytest.raises(TypeError, match="artifact_url"):
        parse_release_manifest(payload)


def test_parse_release_manifest_rejects_invalid_format() -> None:
    payload = _manifest_dict()
    _first_target(payload)["format"] = "raw-bin"

    with pytest.raises(ValueError, match="format"):
        parse_release_manifest(payload)


def test_parse_release_manifest_rejects_invalid_size_bytes() -> None:
    payload = _manifest_dict()
    _first_target(payload)["size_bytes"] = 0

    with pytest.raises(ValueError, match="size_bytes"):
        parse_release_manifest(payload)


def test_parse_release_manifest_rejects_non_object_minimum_consumer_versions() -> None:
    payload = _manifest_dict()
    _first_target(payload)["minimum_consumer_versions"] = "0.6.0"

    with pytest.raises(TypeError, match="minimum_consumer_versions"):
        parse_release_manifest(payload)


def test_parse_release_manifest_rejects_invalid_pyglaze_version_constraint() -> None:
    payload = _manifest_dict()
    _first_target(payload)["minimum_consumer_versions"] = {"pyglaze": "not-semver"}

    with pytest.raises(ValueError, match=r"minimum_consumer_versions\.pyglaze"):
        parse_release_manifest(payload)


def test_parse_release_manifest_rejects_non_string_pyglaze_version_constraint() -> None:
    payload = _manifest_dict()
    _first_target(payload)["minimum_consumer_versions"] = {"pyglaze": 3}

    with pytest.raises(TypeError, match="pyglaze"):
        parse_release_manifest(payload)


def test_parse_release_manifest_rejects_non_release_managed_target() -> None:
    payload = _manifest_dict()
    _first_target(payload)["firmware_target"] = "dev-nucleo-f446re"

    with pytest.raises(ValueError, match="non-release-managed"):
        parse_release_manifest(payload)


def test_select_release_for_target_exact_match() -> None:
    result = select_release_for_target(_manifest_dict(), "le-2-3-0")

    assert result.status is CatalogSelectionStatus.SELECTED
    assert result.target is not None
    assert result.target.firmware_target == "le-2-3-0"
    assert result.target.artifact_format == "mcuboot-signed-bin"
    assert result.required_consumer_versions == {"pyglaze": "0.6.0"}
    assert result.unmet_consumers == {}
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
    _first_target(payload)["minimum_consumer_versions"] = {"pyglaze": "9.9.9"}

    result = select_release_for_target(payload, "le-2-3-0")

    assert result.status is CatalogSelectionStatus.CONSUMER_UPGRADE_REQUIRED
    assert result.target is not None
    assert result.target.min_pyglaze_version == "9.9.9"
    assert result.required_consumer_versions == {"pyglaze": "9.9.9"}
    assert result.unmet_consumers == {"pyglaze": "9.9.9"}


def test_select_release_for_target_passes_when_pyglaze_version_satisfied() -> None:
    result = select_release_for_target(_manifest_dict(), "le-2-3-0")

    assert result.status is CatalogSelectionStatus.SELECTED


def test_select_release_for_target_passes_when_no_version_constraint() -> None:
    result = select_release_for_target(_manifest_dict(), "le-3-0-0")

    assert result.status is CatalogSelectionStatus.SELECTED


def test_select_release_for_device_info_uses_reported_firmware_target() -> None:
    result = select_release_for_device_info(
        _manifest_dict(),
        SimpleNamespace(firmware_target="le-2-3-0"),
    )

    assert result.status is CatalogSelectionStatus.SELECTED


def test_select_release_for_device_info_accepts_mapping_payload() -> None:
    result = select_release_for_device_info(
        _manifest_dict(),
        {"firmware_target": "le-2-3-0"},
    )

    assert result.status is CatalogSelectionStatus.SELECTED


def test_select_release_for_device_info_reports_known_non_release_managed_target() -> (
    None
):
    result = select_release_for_device_info(
        _manifest_dict(),
        SimpleNamespace(firmware_target="dev-nucleo-f446re"),
    )

    assert result.status is CatalogSelectionStatus.NON_RELEASE_MANAGED_TARGET
