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
:module: utils

:synopsis: Encapsulate all constants used for XCP handling

.. currentmodule:: utils
"""
import collections
import enum

VarMap = collections.namedtuple("VarMap", ["format", "size", "byte_order"])

#: declare all available real type
REAL_TYPE_MAP = {
    "float": VarMap(format="f", size=4, byte_order=">"),
    "double": VarMap(format="d", size=8, byte_order=">"),
}

#: declare all available signed type
SIGNED_TYPE_MAP = {
    "int8": VarMap(format="b", size=1, byte_order=">"),
    "int16": VarMap(format="h", size=2, byte_order=">"),
    "int32": VarMap(format="i", size=4, byte_order=">"),
}

#: declare all available unsigned type
UNSIGNED_TYPE_MAP = {
    "uint8": VarMap(format="B", size=1, byte_order=">"),
    "uint16": VarMap(format="H", size=2, byte_order=">"),
    "uint32": VarMap(format="I", size=4, byte_order=">"),
}


class XcpCanSettings(enum.IntEnum):
    """Encapsulate data pointer settings."""

    #: minimum payload limit
    PAYLOAD_LIMIT = 8
    #: XCP packet PID max length (here only ODT compose the PID)
    PID_LENGTH = 1
    #: XCP packet max length
    PACKET_PAYLOAD = 64


class PointerSettings(enum.IntEnum):
    """Encapsulate data pointer settings."""

    #: variable extension address
    EXT_ADDRESS = 0
    #: Position of bit in 32-bit variable referenced by the address
    VAR_OFFSET = 0xFF


class DaqListSettings(enum.IntEnum):
    """Encapsulate DAQ list configuration."""

    #: DAQ mode
    MODE = 0
    #: DAQ prescaler
    PRESCALER = 1
    #: DAQ priority
    PRIORITY = 0


class AcqCommands(enum.IntEnum):
    """Encapslate acquisition commands."""

    #: stop all DAQ acquisition
    STOP_ALL = 0
    #: start previous selected DAQ
    START_SELECTED = 1
    #: stp previous selected DAQ
    STOP_SELECTED = 2


class AcqTasks(enum.IntEnum):
    """Encapsulate all pre-defined DAQ event."""

    #: DAQ 0: 1ms task event
    ONE_MS = 0
    #: DAQ 1: 10ms task event
    TEN_MS = 1
    #: DAQ 2: 100ms task event
    HUNDRED_MS = 2
    #: DAQ 0: 500ms task event
    FIVE_HUNDRED_MS = 3


class StartStopDaqList(enum.IntEnum):
    """Encapsulate DAQ list commands."""

    #: stop DAQ list
    STOP = 0
    #: start DAQ list
    START = 1
    #: select DAQ list
    SELECT = 2
