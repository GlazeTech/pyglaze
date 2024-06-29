# Pyglaze
Pyglaze is a python library used to operate the devices of [Glaze Technologies](https://www.glazetech.dk/).

Documentation can be found [here](https://glazetech.github.io/pyglaze/).

# Installation

To install the latest version of the package, simply run 

```
pip install pyglaze
```

# Usage 
See [this tutorial](https://glazetech.github.io/pyglaze/).

# Developers

To install the API with development tools, first clone the repository from our [public GitHub repository](https://github.com/GlazeTech/pyglaze). Then, from the root of the project, run

```
pip install .[dev, docs]
```

Furthermore, for developers using VS Code, to install the API in editable mode run

```
pip install -e .[dev] --config-settings editable_mode=strict
```

The last config settings are required for Pylance to find the package.

## Documentation - local build
To build and serve the documentation locally

1. Checkout the repository (or a specific version)
2. Install `mkdocs`
3. Run `mkdocs serve` while standing in the project root.


# Bug reporting or feature requests
Please create an issue [here](https://github.com/GlazeTech/pyglaze/issues) and we will look at it ASAP!