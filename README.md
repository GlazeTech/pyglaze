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


# Bug reporting or feature requests
Please create an issue [here](https://github.com/GlazeTech/pyglaze/issues) and we will look at it ASAP!