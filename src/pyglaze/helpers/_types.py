from typing import Any, TypeAlias, TypeVar

import numpy as np

FloatArray: TypeAlias = np.ndarray[Any, np.dtype[np.float64 | np.float32]]
ComplexArray: TypeAlias = (
    np.ndarray[Any, np.dtype[np.complex128 | np.complex64]] | FloatArray
)
F = TypeVar("F", FloatArray, float)
C = TypeVar("C", ComplexArray, complex)


JSONConvertible: TypeAlias = (
    list["JSONConvertible"] | dict[str, "JSONConvertible"] | int | float | str | None
)
