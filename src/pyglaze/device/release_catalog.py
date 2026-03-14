from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
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
    "select_release_for_target",
]


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
    min_pyglaze_version: str | None = None


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

    if target.min_pyglaze_version is not None:
        current = semver.Version.parse(__version__)
        required = semver.Version.parse(target.min_pyglaze_version.removeprefix("v"))
        if current < required:
            return CatalogSelectionResult(
                status=CatalogSelectionStatus.CONSUMER_UPGRADE_REQUIRED,
                target=target,
                device_firmware_target=normalized_target,
            )

    return CatalogSelectionResult(
        status=CatalogSelectionStatus.SELECTED,
        target=target,
        device_firmware_target=normalized_target,
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
    if firmware_target.startswith("dev-"):
        msg = "manifest targets must not include internal-only dev-* firmware_target values"
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

    raw_mcv = target.get("minimum_consumer_versions")
    min_pyglaze = None
    if raw_mcv is not None:
        if not isinstance(raw_mcv, Mapping):
            msg = "minimum_consumer_versions must be an object"
            raise TypeError(msg)
        min_versions = cast("Mapping[str, object]", raw_mcv)
        raw_min_pyglaze = min_versions.get("pyglaze")
        if raw_min_pyglaze is not None:
            min_pyglaze = _expect_semver_str(
                {"pyglaze": raw_min_pyglaze},
                "pyglaze",
                field_name="minimum_consumer_versions.pyglaze",
            )

    return FirmwareReleaseTarget(
        firmware_target=firmware_target,
        display_name=_expect_str(target, "display_name"),
        artifact_name=_expect_str(target, "artifact_name"),
        artifact_url=_expect_str(target, "artifact_url"),
        sha256=_expect_str(target, "sha256"),
        size_bytes=size_bytes,
        min_pyglaze_version=min_pyglaze if isinstance(min_pyglaze, str) else None,
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
