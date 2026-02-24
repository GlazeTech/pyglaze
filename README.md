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

Clone the repository from our [public GitHub repository](https://github.com/GlazeTech/pyglaze), then install in editable mode with all dev dependencies using [uv](https://docs.astral.sh/uv/):

```
uv sync --all-extras
```

This gives you linting, type checking, testing, and docs tools. Run tests with:

```
uv run pytest
```

## Documentation - local build

```
uv run mkdocs serve
```

## MimLink protocol schema sync

> Most developers do not need this. The generated `envelope_pb2.py` is committed
> to the repository. This section is only relevant when syncing `envelope.proto`
> from the upstream MimLink repo.

`pyglaze` vendors the MimLink protobuf schema in
`src/pyglaze/mimlink/proto/envelope.proto`. Python codegen is handled by
[buf](https://buf.build/docs/cli/installation/), which must be installed
separately (e.g. `brew install bufbuild/buf/buf`).

When syncing with upstream MimLink:

1. Replace `src/pyglaze/mimlink/proto/envelope.proto` from upstream.
2. Run `./scripts/generate_mimlink_proto.sh`.
3. Commit the updated `envelope_pb2.py`.
4. Run protocol tests: `uv run pytest tests/mimlink/`.


# Bug reporting or feature requests
Please create an issue [here](https://github.com/GlazeTech/pyglaze/issues) and we will look at it ASAP!
