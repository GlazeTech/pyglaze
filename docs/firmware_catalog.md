# Firmware Catalogs

`pyglaze` can validate the core `manifest.json` fields it relies on for safe
selection, and select the installable artifact that matches a device's canonical
`firmware_target`.

`pyglaze` does not fetch `manifest.json` or download release assets in this
workflow. A caller such as `glaze-desktop` should fetch the manifest and pass it
to `pyglaze`.

## Parse a Catalog

```py
from pyglaze.device import parse_release_manifest

manifest = parse_release_manifest(
    {
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
                "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "size_bytes": 262144,
                "format": "mcuboot-signed-bin",
                "support_status": "legacy",
                "release_profile": "stable",
            }
        ],
    }
)

print(manifest.release_version)
print(manifest.targets[0].artifact_name)
```

## Select for a Known Target

```py
from pyglaze.device import select_release_for_target

result = select_release_for_target(manifest, "le-2-3-0")
print(result.status.value)
print(result.target.artifact_url if result.target is not None else "no match")
print(result.warning_legacy_support)
```

## Select for a Connected Device

For a live device, use `FirmwareClient.select_compatible_release(...)`. The
caller still provides the already-fetched manifest, and `pyglaze` reads the
device's `firmware_target` over MimLink before applying the same exact-match
selection logic and consumer-version checks.
