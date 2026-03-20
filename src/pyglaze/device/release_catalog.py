from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Union, cast

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

_KNOWN_NON_RELEASE_MANAGED_TARGETS = frozenset({"dev-nucleo-f446re"})


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
    support_status: str | None = None
    release_profile: str | None = None
    minimum_consumer_versions: dict[str, str] = field(default_factory=dict)

    @property
    def min_pyglaze_version(self) -> str | None:
        """Backward-compatible alias for the pyglaze minimum-version gate."""
        return self.minimum_consumer_versions.get("pyglaze")


@dataclass(frozen=True)
class FirmwareReleaseManifest:
    """Validated firmware release catalog."""

    release_version: str
    channel: str
    published_at: str
    targets: tuple[FirmwareReleaseTarget, ...]


@dataclass(frozen=True)
class CatalogSelectionResult:
    """Selection outcome for a specific device target."""

    status: CatalogSelectionStatus
    target: FirmwareReleaseTarget | None
    device_firmware_target: str
    required_consumer_versions: dict[str, str] = field(default_factory=dict)
    unmet_consumers: dict[str, str] = field(default_factory=dict)
    warning_legacy_support: bool = False


ManifestSource = Union[
    FirmwareReleaseManifest,
    str,
    Mapping[str, object],
]


def parse_release_manifest(source: ManifestSource) -> FirmwareReleaseManifest:
    """Parse and validate a firmware release manifest."""
    if isinstance(source, FirmwareReleaseManifest):
        return source

    payload = _load_manifest_payload(source)

    if payload.get("schema_version") != 1:
        msg = "manifest schema_version must be 1"
        raise ValueError(msg)

    if payload.get("product") != "mimos":
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
        release_version=_expect_str(payload, "release_version"),
        channel=channel,
        published_at=_expect_str(payload, "published_at"),
        targets=targets,
    )


def select_release_for_target(
    manifest: ManifestSource,
    firmware_target: str,
) -> CatalogSelectionResult:
    """Select the compatible release entry for a canonical firmware target.

    Args:
        manifest: Parsed manifest object or raw manifest payload.
        firmware_target: Canonical device firmware target to match.
    """
    parsed_manifest = parse_release_manifest(manifest)
    normalized_target = firmware_target.strip()

    if normalized_target in _KNOWN_NON_RELEASE_MANAGED_TARGETS:
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

    required_consumer_versions = dict(target.minimum_consumer_versions)
    unmet_consumers: dict[str, str] = {}
    raw_min_pyglaze = required_consumer_versions.get("pyglaze")
    if raw_min_pyglaze is not None:
        current = semver.Version.parse(__version__.removeprefix("v"))
        required = semver.Version.parse(raw_min_pyglaze.removeprefix("v"))
        if current < required:
            unmet_consumers["pyglaze"] = raw_min_pyglaze

    return CatalogSelectionResult(
        status=(
            CatalogSelectionStatus.CONSUMER_UPGRADE_REQUIRED
            if unmet_consumers
            else CatalogSelectionStatus.SELECTED
        ),
        target=target,
        device_firmware_target=normalized_target,
        required_consumer_versions=required_consumer_versions,
        unmet_consumers=unmet_consumers,
        warning_legacy_support=target.support_status == "legacy",
    )


def select_release_for_device_info(
    manifest: ManifestSource,
    device_info: object,
) -> CatalogSelectionResult:
    """Select the compatible release entry for a device-info payload."""
    return select_release_for_target(
        manifest,
        _extract_device_firmware_target(device_info),
    )


def _load_manifest_payload(
    source: str | Mapping[str, object],
) -> dict[str, object]:
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

    target = cast("dict[str, object]", payload)
    firmware_target = _expect_str(target, "firmware_target")
    if firmware_target in _KNOWN_NON_RELEASE_MANAGED_TARGETS:
        msg = (
            "manifest targets must not include known non-release-managed "
            "firmware_target values"
        )
        raise ValueError(msg)

    format_name = _expect_str(target, "format")
    if format_name != "mcuboot-signed-bin":
        msg = "format must be 'mcuboot-signed-bin'"
        raise ValueError(msg)

    size_bytes = target.get("size_bytes")
    if (
        not isinstance(size_bytes, int)
        or isinstance(size_bytes, bool)
        or size_bytes <= 0
    ):
        msg = "size_bytes must be a positive integer"
        raise ValueError(msg)

    minimum_consumer_versions: dict[str, str] = {}
    raw_mcv = target.get("minimum_consumer_versions")
    if raw_mcv is not None:
        if not isinstance(raw_mcv, Mapping):
            msg = "minimum_consumer_versions must be an object"
            raise TypeError(msg)
        min_versions = cast("Mapping[str, object]", raw_mcv)
        for consumer_name, required_version in min_versions.items():
            minimum_consumer_versions[consumer_name] = _expect_semver_str(
                {consumer_name: required_version},
                consumer_name,
                field_name=f"minimum_consumer_versions.{consumer_name}",
            )

    return FirmwareReleaseTarget(
        firmware_target=firmware_target,
        display_name=_expect_str(target, "display_name"),
        artifact_name=_expect_str(target, "artifact_name"),
        artifact_url=_expect_str(target, "artifact_url"),
        sha256=_expect_str(target, "sha256"),
        size_bytes=size_bytes,
        artifact_format=format_name,
        support_status=_expect_optional_enum(
            target,
            "support_status",
            allowed_values={"active", "legacy"},
        ),
        release_profile=_expect_optional_str(target, "release_profile"),
        minimum_consumer_versions=minimum_consumer_versions,
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
    value = payload.get(key)
    if not isinstance(value, str):
        msg = f"{key} is required and must be a string"
        raise TypeError(msg)
    stripped = value.strip()
    if not stripped:
        msg = f"{key} must be a non-empty string"
        raise ValueError(msg)
    return stripped


def _expect_optional_str(payload: Mapping[str, object], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    return _expect_str(payload, key)


def _expect_optional_enum(
    payload: Mapping[str, object],
    key: str,
    *,
    allowed_values: set[str],
) -> str | None:
    value = _expect_optional_str(payload, key)
    if value is None:
        return None
    if value not in allowed_values:
        allowed = ", ".join(sorted(allowed_values))
        msg = f"{key} must be one of {allowed}"
        raise ValueError(msg)
    return value


def _expect_semver_str(
    payload: Mapping[str, object],
    key: str,
    *,
    field_name: str | None = None,
) -> str:
    value = _expect_str(payload, key)
    field_label = field_name or key
    try:
        semver.Version.parse(value.removeprefix("v"))
    except ValueError as exc:
        msg = f"{field_label} must be a valid semantic version"
        raise ValueError(msg) from exc
    return value


def _extract_device_firmware_target(device_info: object) -> str:
    if isinstance(device_info, Mapping):
        return _expect_str(device_info, "firmware_target")

    raw_firmware_target = getattr(device_info, "firmware_target", None)
    if not isinstance(raw_firmware_target, str):
        msg = "device_info.firmware_target is required and must be a string"
        raise TypeError(msg)

    normalized_target = raw_firmware_target.strip()
    if not normalized_target:
        msg = "device_info.firmware_target must be a non-empty string"
        raise ValueError(msg)
    return normalized_target
