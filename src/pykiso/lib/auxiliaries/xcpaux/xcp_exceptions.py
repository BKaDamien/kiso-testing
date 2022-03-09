##########################################################################
# Copyright (c) 2010-2022 Robert Bosch GmbH
#
# This source code is copyright protected and proprietary
# to Robert Bosch GmbH. Only those rights that have been
# explicitly granted to you by Robert Bosch GmbH in written
# form may be exercised. All other rights remain with
# Robert Bosch GmbH.
##########################################################################

"""
:module: xcp_exceptions

:synopsis: Custom exceptions for XCP handling errors.

.. currentmodule:: xcp_exceptions
"""


class XcpError(Exception):
    """General XCP specific exception used as basis for all others."""

    def __str__(self):
        return self.message


class InvalidSymbolTypeError(XcpError):
    """Raised when the symbol's type is not supported."""

    def __init__(self, symbol_type: str, symbol_name: str) -> None:
        """Initialize attributes.

        :param symbol_type: symbol's type (STRUCT, REAL...)
        :param symbol_name: symbol's name
        """
        self.message = f"Unsupported type {symbol_type} for symbol {symbol_name}"
        super().__init__(self.message)


class UnknownSymbolError(XcpError):
    """Raised when the symbols is not in the simplified A2L file."""

    def __init__(self, symbol_name: str) -> None:
        """Initialize attributes.

        :param symbol_name: symbol's name
        """
        self.message = f"Symbol {symbol_name} doesn't exist"
        super().__init__(self.message)
