# Documentation

Documentation can be found [here](https://glazetech.github.io/App/).

# Install the Glaze API

It is currently not possible to store python packages in a private Github repository (see [this](https://github.com/community/community/discussions/8542). Therefore, to install the API using `pip`, run

```
pip install git+https://github.com/GlazeTech/App.git@v<DESIRED_VERSION>
```
where available versions (for `<DESIRED_VERSION>`) are shown [here](https://github.com/GlazeTech/App/tags).

# Developers

To install the API with development tools, run

```
pip install .[dev, docs]
```

Furthermore, for developers using VS Code, to install the API in editable mode run

```
pip install -e .[dev] --config-settings editable_mode=strict
```

The last config settings are required for Pylance to find the package.

# Bug reporting or feature requests
Please create an issue [here](https://github.com/GlazeTech/App/issues) and we will look at it ASAP!