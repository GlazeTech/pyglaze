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

> Most developers do not need this. The generated `envelope_pb2.py` is committed
> to the repository. This section is only relevant when syncing `envelope.proto`
> from the upstream MimLink repo.

`pyglaze` vendors the MimLink protobuf schema in
`src/pyglaze/mimlink/proto/envelope.proto`. Python codegen is handled by
[buf](https://buf.build/docs/cli/installation/), which must be installed
separately (e.g. `brew install bufbuild/buf/buf`). The Python protobuf code
generator is pinned in `buf.gen.yaml` to
`buf.build/protocolbuffers/python:v33.0`, while the type-stub generator comes
from the project Python dev environment.

When syncing with upstream MimLink:

1. Replace `src/pyglaze/mimlink/proto/envelope.proto` from upstream.
2. Ensure the project dev environment is installed so `protoc-gen-mypy` is
   available in `.venv/bin`.
3. Run `./scripts/generate_mimlink_proto.sh`.
4. Commit the updated `envelope_pb2.py` and `envelope_pb2.pyi`.
5. Run protocol tests: `uv run --extra dev pytest tests/mimlink/`.


# Bug reporting or feature requests
Please create an issue [here](https://github.com/GlazeTech/pyglaze/issues) and we will look at it ASAP!