from typing import Any, TypeVar, Union

import numpy as np
from typing_extensions import ParamSpec, TypeAlias

# numpy typing does not work with pipe, hence Union instead
FloatArray: TypeAlias = np.ndarray[Any, np.dtype[Union[np.float64, np.float32]]]
ComplexArray: TypeAlias = Union[
    np.ndarray[Any, np.dtype[Union[np.complex128, np.complex64]]], FloatArray
]
F = TypeVar("F", FloatArray, float)
C = TypeVar("C", ComplexArray, complex)


P = ParamSpec("P")
T = TypeVar("T")

JSONConvertible: TypeAlias = Union[
    list["JSONConvertible"], dict[str, "JSONConvertible"], int, float, str, None
]
