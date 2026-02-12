# Pyglaze
Pyglaze is a python library used to operate the devices of [Glaze Technologies](https://www.glazetech.dk/).

Documentation can be found [here](https://glazetech.github.io/pyglaze/latest/).

# Installation

To install the latest version of the package, simply run 

```
pip install pyglaze
```

# Usage 
See [our documentation](https://glazetech.github.io/pyglaze/latest/) for usage.

# Developers

To install the API with development tools in editable mode, first clone the repository from our [public GitHub repository](https://github.com/GlazeTech/pyglaze). Then, from the root of the project, run

```
python -m pip install --upgrade pip
pip install -e . --config-settings editable_mode=strict
pip install -r requirements-dev.txt
```

## Documentation - local build
To build and serve the documentation locally

1. Checkout the repository (or a specific version)
2. Install `mkdocs`
3. Run `mkdocs serve` while standing in the project root.

## MimLink protocol schema sync
`pyglaze` vendors the MimLink protobuf schema in
`src/pyglaze/mimlink/proto/envelope.proto`.

Generation is orchestrated with `buf` and local `protoc` plugins.

Generated files that must be committed:

1. `src/pyglaze/mimlink/proto/envelope_pb2.py`
2. `src/pyglaze/mimlink/proto/nanopb/envelope.pb.h`
3. `src/pyglaze/mimlink/proto/nanopb/envelope.pb.c`

Required tools:

1. `buf`
2. `protoc`
3. `protoc-gen-nanopb` (installed by `uv sync --extra dev`)

When syncing with upstream MimLink:

1. Replace `src/pyglaze/mimlink/proto/envelope.proto`.
2. Replace `src/pyglaze/mimlink/proto/envelope.options` if nanopb options changed.
3. Run `./scripts/generate_mimlink_proto.sh`.
4. Commit all generated files listed above.
5. Run protocol tests (`pytest tests/mimlink`).

Troubleshooting:

1. If `protoc-gen-nanopb` is missing, run `uv sync --extra dev` and retry.
2. CI enforces `buf lint` and generated-file drift checks, so stale generated files fail validation.


# Bug reporting or feature requests
Please create an issue [here](https://github.com/GlazeTech/pyglaze/issues) and we will look at it ASAP!
