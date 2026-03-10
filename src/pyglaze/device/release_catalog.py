from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

import semver

from pyglaze import __version__

__all__ = [
    "CatalogSelectionResult",
    "CatalogSelectionStatus",
    "FirmwareReleaseManifest",
    "FirmwareReleaseTarget",
    "parse_release_manifest",
    "select_release_for_device_info",
    "select_release_for_target",
]


class DeviceTargetInfo(Protocol):
    """Object exposing a canonical firmware target."""

    firmware_target: str


class CatalogSelectionStatus(str, Enum):
    """Outcome of catalog selection for a device target."""

    SELECTED = "selected"
    NON_RELEASE_MANAGED_TARGET = "non_release_managed_target"
    NO_COMPATIBLE_RELEASE = "no_compatible_release"
    CONSUMER_UPGRADE_REQUIRED = "consumer_upgrade_required"


@dataclass(frozen=True)
class FirmwareReleaseTarget:
    """One installable firmware target entry from a release manifest."""

    firmware_target: str
    display_name: str
    artifact_name: str
    artifact_url: str
    sha256: str
    size_bytes: int
    artifact_format: str
    product_models: tuple[str, ...] = ()
    support_status: str | None = None
    release_profile: str | None = None
    feature_flags: dict[str, str] = field(default_factory=dict)
    hardware_type: str | None = None
    hardware_revision: str | int | None = None
    bootloader: str | None = None
    signing: str | None = None
    minimum_consumer_versions: dict[str, str] = field(default_factory=dict)
    notes: str | None = None


@dataclass(frozen=True)
class FirmwareReleaseManifest:
    """Validated firmware release catalog."""

    schema_version: int
    product: str
    release_version: str
    channel: str
    published_at: str
    targets: tuple[FirmwareReleaseTarget, ...]
    commit: str | None = None
    source_tag: str | None = None
    notes_url: str | None = None


@dataclass(frozen=True)
class CatalogSelectionResult:
    """Selection outcome for a specific device target."""

    status: CatalogSelectionStatus
    target: FirmwareReleaseTarget | None
    device_firmware_target: str
    required_consumer_versions: dict[str, str] = field(default_factory=dict)
    unmet_consumers: dict[str, str] = field(default_factory=dict)
    warning_legacy_support: bool = False


ManifestSource = FirmwareReleaseManifest | str | bytes | Mapping[str, object]


def parse_release_manifest(source: ManifestSource) -> FirmwareReleaseManifest:
    """Parse and validate a firmware release manifest."""
    if isinstance(source, FirmwareReleaseManifest):
        return source

    payload = _load_manifest_payload(source)
    schema_version = _expect_int(payload, "schema_version")
    if schema_version != 1:
        msg = "manifest schema_version must be 1"
        raise ValueError(msg)

    product = _expect_str(payload, "product")
    if product != "mimos":
        msg = "manifest product must be 'mimos'"
        raise ValueError(msg)

    channel = _expect_str(payload, "channel")
    if channel not in {"stable", "edge", "rc"}:
        msg = "manifest channel must be one of stable, edge, rc"
        raise ValueError(msg)

    targets_payload = payload.get("targets")
    if not isinstance(targets_payload, list):
        msg = "manifest targets must be a list"
        raise TypeError(msg)

    targets = tuple(_parse_target(entry) for entry in targets_payload)
    _validate_unique_targets(targets)

    return FirmwareReleaseManifest(
        schema_version=schema_version,
        product=product,
        release_version=_expect_str(payload, "release_version"),
        channel=channel,
        published_at=_expect_str(payload, "published_at"),
        targets=targets,
        commit=_optional_str(payload, "commit"),
        source_tag=_optional_str(payload, "source_tag"),
        notes_url=_optional_str(payload, "notes_url"),
    )


def select_release_for_target(
    manifest: ManifestSource,
    firmware_target: str,
) -> CatalogSelectionResult:
    """Select the compatible release entry for a canonical firmware target."""
    parsed_manifest = parse_release_manifest(manifest)
    normalized_target = _normalize_non_empty_string(
        firmware_target, field_name="firmware_target"
    )
    if normalized_target.startswith("dev-"):
        return CatalogSelectionResult(
            status=CatalogSelectionStatus.NON_RELEASE_MANAGED_TARGET,
            target=None,
            device_firmware_target=normalized_target,
        )

    target = next(
        (
            candidate
            for candidate in parsed_manifest.targets
            if candidate.firmware_target == normalized_target
        ),
        None,
    )
    if target is None:
        return CatalogSelectionResult(
            status=CatalogSelectionStatus.NO_COMPATIBLE_RELEASE,
            target=None,
            device_firmware_target=normalized_target,
        )

    unmet_consumers = _compute_unmet_consumers(target.minimum_consumer_versions)
    if unmet_consumers:
        return CatalogSelectionResult(
            status=CatalogSelectionStatus.CONSUMER_UPGRADE_REQUIRED,
            target=target,
            device_firmware_target=normalized_target,
            required_consumer_versions=target.minimum_consumer_versions,
            unmet_consumers=unmet_consumers,
            warning_legacy_support=target.support_status == "legacy",
        )

    return CatalogSelectionResult(
        status=CatalogSelectionStatus.SELECTED,
        target=target,
        device_firmware_target=normalized_target,
        required_consumer_versions=target.minimum_consumer_versions,
        warning_legacy_support=target.support_status == "legacy",
    )


def select_release_for_device_info(
    manifest: ManifestSource,
    device_info: DeviceTargetInfo,
) -> CatalogSelectionResult:
    """Select the compatible release entry for a device-info object."""
    return select_release_for_target(manifest, device_info.firmware_target)


def _load_manifest_payload(
    source: str | bytes | Mapping[str, object],
) -> Mapping[str, Any]:
    if isinstance(source, bytes):
        try:
            source = source.decode("utf-8")
        except UnicodeDecodeError as exc:
            msg = "manifest bytes must be valid UTF-8"
            raise ValueError(msg) from exc

    if isinstance(source, str):
        try:
            payload = json.loads(source)
        except json.JSONDecodeError as exc:
            msg = "manifest is not valid JSON"
            raise ValueError(msg) from exc
    else:
        payload = dict(source)

    if not isinstance(payload, dict):
        msg = "manifest root must be a JSON object"
        raise TypeError(msg)
    return payload


def _parse_target(payload: object) -> FirmwareReleaseTarget:
    if not isinstance(payload, dict):
        msg = "manifest target entries must be objects"
        raise TypeError(msg)

    support_status = _optional_str(payload, "support_status")
    if support_status is not None and support_status not in {"active", "legacy"}:
        msg = "target support_status must be active or legacy"
        raise ValueError(msg)

    format_name = _expect_str(payload, "format")
    if format_name != "mcuboot-signed-bin":
        msg = "target format must be 'mcuboot-signed-bin'"
        raise ValueError(msg)

    minimum_consumer_versions = _optional_str_mapping(
        payload,
        "minimum_consumer_versions",
    )
    for consumer_name, version in minimum_consumer_versions.items():
        _parse_version(version, field_name=f"minimum_consumer_versions.{consumer_name}")

    return FirmwareReleaseTarget(
        firmware_target=_expect_str(payload, "firmware_target"),
        display_name=_expect_str(payload, "display_name"),
        artifact_name=_expect_str(payload, "artifact_name"),
        artifact_url=_expect_str(payload, "artifact_url"),
        sha256=_expect_str(payload, "sha256"),
        size_bytes=_expect_int(payload, "size_bytes"),
        artifact_format=format_name,
        product_models=_optional_str_sequence(payload, "product_models"),
        support_status=support_status,
        release_profile=_optional_str(payload, "release_profile"),
        feature_flags=_optional_str_mapping(payload, "feature_flags"),
        hardware_type=_optional_str(payload, "hardware_type"),
        hardware_revision=_optional_scalar(payload, "hardware_revision"),
        bootloader=_optional_str(payload, "bootloader"),
        signing=_optional_str(payload, "signing"),
        minimum_consumer_versions=minimum_consumer_versions,
        notes=_optional_str(payload, "notes"),
    )


def _validate_unique_targets(targets: tuple[FirmwareReleaseTarget, ...]) -> None:
    seen: set[str] = set()
    for target in targets:
        if target.firmware_target in seen:
            msg = (
                f"manifest contains duplicate firmware_target: {target.firmware_target}"
            )
            raise ValueError(msg)
        seen.add(target.firmware_target)


def _expect_str(payload: Mapping[str, object], key: str) -> str:
    if key not in payload:
        msg = f"{key} is required"
        raise ValueError(msg)
    return _normalize_non_empty_string(payload[key], field_name=key)


def _optional_str(payload: Mapping[str, object], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    return _normalize_non_empty_string(value, field_name=key)


def _expect_int(payload: Mapping[str, object], key: str) -> int:
    if key not in payload:
        msg = f"{key} is required"
        raise ValueError(msg)
    value = payload[key]
    if isinstance(value, bool):
        msg = f"{key} must be an integer"
        raise TypeError(msg)
    if not isinstance(value, int):
        msg = f"{key} must be an integer"
        raise TypeError(msg)
    return value


def _optional_scalar(payload: Mapping[str, object], key: str) -> str | int | None:
    value = payload.get(key)
    if value is None:
        return None
    if isinstance(value, bool):
        msg = f"{key} must be a string or integer"
        raise TypeError(msg)
    if isinstance(value, int):
        return value
    return _normalize_non_empty_string(value, field_name=key)


def _optional_str_sequence(payload: Mapping[str, object], key: str) -> tuple[str, ...]:
    value = payload.get(key)
    if value is None:
        return ()
    if not isinstance(value, list):
        msg = f"{key} must be a list of strings"
        raise TypeError(msg)
    return tuple(_normalize_non_empty_string(item, field_name=key) for item in value)


def _optional_str_mapping(payload: Mapping[str, object], key: str) -> dict[str, str]:
    value = payload.get(key)
    if value is None:
        return {}
    if not isinstance(value, dict):
        msg = f"{key} must be an object mapping strings to strings"
        raise TypeError(msg)

    normalized: dict[str, str] = {}
    for raw_key, raw_value in value.items():
        normalized_key = _normalize_non_empty_string(raw_key, field_name=key)
        normalized_value = _normalize_non_empty_string(raw_value, field_name=key)
        normalized[normalized_key] = normalized_value
    return normalized


def _normalize_non_empty_string(value: object, *, field_name: str) -> str:
    if not isinstance(value, str):
        msg = f"{field_name} must be a string"
        raise TypeError(msg)
    normalized = value.strip()
    if normalized == "":
        msg = f"{field_name} must be a non-empty string"
        raise ValueError(msg)
    return normalized


def _compute_unmet_consumers(
    minimum_consumer_versions: Mapping[str, str],
) -> dict[str, str]:
    if "pyglaze" not in minimum_consumer_versions:
        return {}

    minimum_version = minimum_consumer_versions["pyglaze"]
    current = _parse_version(__version__, field_name="pyglaze")
    required = _parse_version(
        minimum_version, field_name="minimum_consumer_versions.pyglaze"
    )
    if current < required:
        return {"pyglaze": minimum_version}
    return {}


def _parse_version(version: str, *, field_name: str) -> semver.Version:
    normalized = version.strip().removeprefix("v")
    try:
        return semver.Version.parse(normalized)
    except ValueError as exc:
        msg = f"{field_name} must be a valid semantic version"
        raise ValueError(msg) from exc
