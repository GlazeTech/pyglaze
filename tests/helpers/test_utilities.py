from __future__ import annotations

import pytest

from pyglaze.helpers import utilities


class TestBackoffRetry:
    def test_no_retries(self: TestBackoffRetry) -> None:
        self.counter = 0

        @utilities._BackoffRetry()
        def f_no_retries() -> str:
            self.counter += 1
            return "Success!"

        assert f_no_retries() == "Success!"
        assert self.counter == 1

    def test_one_retry(self: TestBackoffRetry) -> None:
        self.counter = 0

        @utilities._BackoffRetry()
        def f_one_retry() -> str:
            self.counter += 1
            if self.counter < 2:
                msg = "Error!"
                raise ValueError(msg)
            return "Success!"

        assert f_one_retry() == "Success!"
        assert self.counter == 2

    def test_always_fails(self: TestBackoffRetry) -> None:
        self.counter = 0

        @utilities._BackoffRetry(max_tries=2)
        def f_always_fails() -> None:
            self.counter += 1
            msg = "Error!"
            raise ValueError(msg)

        with pytest.raises(ValueError, match="Error!"):
            f_always_fails()
        assert self.counter == 2
