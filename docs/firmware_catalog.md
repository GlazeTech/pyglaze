# Firmware Catalogs

`pyglaze` can validate a MimOS `manifest.json` catalog and select the installable
artifact that matches a device's canonical `firmware_target`.

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
                "firmware_target": "le23-r1",
                "display_name": "Le 2.3.0",
                "artifact_name": "mimos-le23-r1-v1.0.0.signed.bin",
                "artifact_url": "https://example.invalid/le23.bin",
                "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "size_bytes": 262144,
                "format": "mcuboot-signed-bin",
            }
        ],
    }
)

print(manifest.release_version)
print(manifest.targets[0].artifact_name)
```

## Select for a Known Target

```py
from pyglaze.device import parse_release_manifest, select_release_for_target

manifest = parse_release_manifest(
    {
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
                "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "size_bytes": 262144,
                "format": "mcuboot-signed-bin",
            }
        ],
    }
)

result = select_release_for_target(manifest, "le23-r1")
print(result.status.value)
print(result.target.artifact_url if result.target is not None else "no match")
```

## Select for a Connected Device

For a live device, use `FirmwareClient.select_compatible_release(...)`. The
caller still provides the already-fetched manifest, and `pyglaze` reads the
device's `firmware_target` over MimLink before applying the same exact-match
selection logic.
