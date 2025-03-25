# Copyright (c) 2025, Abilian SAS
from __future__ import annotations

from hop3.services.certificates import RE_DOMAIN_VALIDATOR


def test_domain_validation():
    assert RE_DOMAIN_VALIDATOR.match("example.com")
    assert RE_DOMAIN_VALIDATOR.match("sub.example.com")
    assert RE_DOMAIN_VALIDATOR.match("sub-domain.example.com")
    # FIXME:
    # assert RE_DOMAIN_VALIDATOR.match(
    #     "010-flask-pip-wsgi-1742306604.hop-dev.abilian.com"
    # )
