from __future__ import annotations

import shutil
import uuid
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest
from pyglaze.device import delayunit, load_delayunit
from pyglaze.device.delayunit import _load_delayunit_from_path
from scipy.interpolate import CubicSpline


@pytest.fixture()
def uniform_delay() -> delayunit.UniformDelay:
    return delayunit.UniformDelay(
        friendly_name="uniform_delay",
        unique_id=uuid.uuid4(),
        creation_time=datetime.now(),  # noqa: DTZ005
        time_window=100e-12,
    )


@pytest.fixture()
def nonuniform_delay() -> delayunit.Delay:
    generator = np.random.default_rng(seed=3)
    return delayunit.NonuniformDelay(
        friendly_name="nonuniform_delay",
        unique_id=uuid.uuid4(),
        creation_time=datetime.now(),  # noqa: DTZ005
        time_window=100e-12,
        residual_interpolator=CubicSpline(x=np.arange(10), y=generator.random(10)),
    )


@pytest.mark.parametrize(
    "test_params",
    [
        {
            "class": "UniformDelay",
            "kwargs": {"time_window": 100e-12, "friendly_name": "uniform_test_name"},
        },
        {
            "class": "NonuniformDelay",
            "kwargs": {
                "time_window": 100e-12,
                "friendly_name": "nonuniform_test_name",
                "residual_interpolator": lambda x: x * 10 + 2,
            },
        },
    ],
)
def test_new_delay(test_params: dict) -> None:
    delay_cls: delayunit.Delay = getattr(delayunit, test_params["class"])
    delay_instance = delay_cls.new(**test_params["kwargs"])  # type: ignore[attr-defined]
    assert isinstance(delay_instance, delayunit.Delay)


def test_load_delayunit() -> None:
    unit = load_delayunit("mock_delay")
    assert isinstance(unit, delayunit.Delay)


@pytest.mark.parametrize("fixture_name", ["uniform_delay", "nonuniform_delay"])
class TestDelays:
    SAVEDIR = Path("delays_test_storage")

    @classmethod
    def teardown_class(cls: type[TestDelays]) -> None:
        shutil.rmtree(cls.SAVEDIR)

    @classmethod
    def setup_class(cls: type[TestDelays]) -> None:
        Path(cls.SAVEDIR).mkdir()

    def test_save_load(
        self: TestDelays, fixture_name: str, request: pytest.FixtureRequest
    ) -> None:
        delay: delayunit.Delay = request.getfixturevalue(fixture_name)
        delay.save(self.SAVEDIR / delay.filename)

        reloaded = _load_delayunit_from_path(self.SAVEDIR / delay.filename)
        assert delay.unique_id == reloaded.unique_id
        assert type(delay) is type(reloaded)

    def test_call(
        self: TestDelays, fixture_name: str, request: pytest.FixtureRequest
    ) -> None:
        delay: delayunit.Delay = request.getfixturevalue(fixture_name)
        x = np.linspace(0, 1, 5)
        y = delay(x)
        assert len(y) == len(x)

    @pytest.mark.parametrize("limits", [[-0.1, 0.5], [0.5, 1.1]])
    def test_wrong_x_values(
        self: TestDelays,
        fixture_name: str,
        limits: list,
        request: pytest.FixtureRequest,
    ) -> None:
        delay: delayunit.Delay = request.getfixturevalue(fixture_name)
        x = np.linspace(limits[0], limits[1], 5)
        with pytest.raises(
            ValueError, match="All values of 'x' must be between 0 and 1."
        ):
            delay(x)
