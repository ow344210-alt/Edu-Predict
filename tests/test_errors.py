"""Error hierarchy: every project error must derive from EduPredictError."""

from __future__ import annotations

import pytest

from edupredict import errors


@pytest.mark.parametrize(
    "exc",
    [
        errors.ConfigurationError,
        errors.InfrastructureError,
        errors.HdfsUnavailableError,
        errors.ImpalaUnavailableError,
        errors.NotImplementedYetError,
    ],
)
def test_all_errors_derive_from_base(exc):
    assert issubclass(exc, errors.EduPredictError)
    assert issubclass(exc, Exception)


def test_infrastructure_errors_are_grouped():
    assert issubclass(errors.HdfsUnavailableError, errors.InfrastructureError)
    assert issubclass(errors.ImpalaUnavailableError, errors.InfrastructureError)


def test_error_carries_message():
    err = errors.ConfigurationError("bad value")
    assert str(err) == "bad value"
