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
:module: xcp_daq

:synopsis: manage the DAQ measurement method

.. currentmodule:: xcp_daq
"""

import collections
import logging
import struct
from dataclasses import dataclass, field
from typing import Any, Generator, List, Optional, Union

from pyxcp.master import Master

from .utils import (
    REAL_TYPE_MAP,
    SIGNED_TYPE_MAP,
    UNSIGNED_TYPE_MAP,
    AcqCommands,
    AcqTasks,
    DaqListSettings,
    PointerSettings,
    StartStopDaqList,
    XcpCanSettings,
)
from .xcp_exceptions import InvalidSymbolTypeError, UnknownSymbolError

log = logging.getLogger(__name__)


@dataclass
class XcpVar:
    """Store all ECU variables information."""

    #: variable'name
    name: str
    #: variable address in target's memory
    address: int
    #: variable's size
    size: int
    #: mapping representing the variable type
    data_type: collections.namedtuple
    #: store the received values from the target
    records: list = field(default_factory=list)
    #: store the current value return during a single target read
    snapshot_value: Optional[Any] = None

    def add_record(self, data: bytes) -> None:
        """Add a value to the records list.

        :param data: value to append
        """
        value = self.from_bytes(data)
        self.records.append(value)

    def from_bytes(self, data: bytes) -> Any:
        """Convert bytes in the corresponding variable type
        (float, int,...).

        :param data: value to convert

        :return: a converted value based on the variable's type
        """
        # unpack return a tuple even if one value is unpacked due to
        # this fact just return the first element
        return struct.unpack(
            f"{self.data_type.byte_order}{self.data_type.format}", data
        )[0]

    def to_bytes(self, data: str) -> bytes:
        """Return a bytes object containing the given value.

        :param data: value to convert

        :return: bytes object representation for the given data
        """
        return struct.pack(f"{self.data_type.byte_order}{self.data_type.format}", data)

    def pop_records(self) -> Generator[Any, None, None]:
        """Yield the records from xpc variable.

        :return: the recorded values
        """
        for value in self.records:
            yield value


@dataclass
class Odt:
    """Represent an ODT container."""

    #: ODT identification number
    number: Optional[int] = None
    #: attached variables
    variables: List[XcpVar] = field(default_factory=list)


@dataclass
class DaqList:
    """Represent a DAQ list container."""

    #: DAQ list identification number
    number: int = None
    #: attached DAQ event (1ms, 10ms...)
    event: int = None
    #: contain all created ODT instances
    odts: list = field(default_factory=list)

    def create_odts(self, variables: List[XcpVar]) -> List[List[XcpVar]]:
        """Create all needed ODTs tables based on the number of
        variables to record.

        :param variables: variables to record

        :return: all created variables in the creation order
        """
        # max payload is equal to CAN FD payload - PID length
        pid = XcpCanSettings.PID_LENGTH
        max_packet = XcpCanSettings.PACKET_PAYLOAD
        payload_size = pid
        odt_count = 0
        current_odt = Odt(number=odt_count)
        self.odts.append(current_odt)

        for var in variables:
            payload_size += var.size
            # if we exceed the max xcp packet length just create a new
            # ODT.
            if payload_size > max_packet:
                odt_count += 1
                payload_size = pid + var.size
                current_odt = Odt(number=odt_count)
                self.odts.append(current_odt)

            current_odt.variables.append(var)

        # just return all created variables in the creation order
        return [odt.variables for odt in self.odts]


class Daq:
    """Manage the DAQ resources allocation (ODT, DAQ list, ODT entries)
    and handle the DAQ recording.
    """

    def __init__(self, symbols: dict, master_xcp: Master) -> None:
        """Initialize attributes.

        :param symbols: loaded symbols from the simplified A2L File
        :param master_xcp: master instance from pyxcp package
        """
        self.master_xcp = master_xcp
        self.symbols = symbols
        self.acq_register = collections.OrderedDict(
            {event.value: list() for event in AcqTasks}
        )
        self.acq_set = list()
        self.odt_set = list()
        self.selected_variables = list()

    def open(self) -> None:
        """Open the XCP connection."""
        self.master_xcp.connect()
        self.master_xcp.getCommModeInfo()

    def close(self) -> None:
        """Close the XCP connection."""
        self.master_xcp.freeDaq()
        self.master_xcp.disconnect()
        self.master_xcp.close()

    def reset_acquisition_ressources(self) -> None:
        """Reset all resources use for the acquisition."""
        self.acq_register = collections.OrderedDict(
            {event.value: list() for event in AcqTasks}
        )
        self.acq_set = list()
        self.odt_set = list()

    def reset_records(self) -> None:
        """Reset all records for all variables."""
        for xcp_var in self.selected_variables:
            if xcp_var.records:
                xcp_var.records = list()

    def register_variable(self, variable: str, event: Union[int, AcqTasks]) -> XcpVar:
        """Register a variable to a define acquisition event (1s, 10ms,
            100ms, or 500ms...)

        :param variable: variable's name
        :param event: acquisition event type to register

        :return: an instance of XcpVar with all the needed information
            (name, type, size....)
        """
        xcp_var = self.select_variable(variable)
        self.acq_register[event].append(xcp_var)
        return xcp_var

    def select_variable(self, variable: str) -> XcpVar:
        """Select the appropriate symbol inside the simplified A2L file
        base on the variable name. If a variable was previously selected
        just return the associate XcpVar instance.

        :param variable: variable to seek for

        :return: an instance of XcpVar with all the needed information
            (name, type, size....)

        :raises UnknownSymbolError: when the variable is not present in
            the loaded simplified A2L
        """

        was_registered, xcp_var = self.is_already_register(variable)

        # if a variable was already registered just use the
        # corresponding XcpVar otherwise seek for it in the simplified
        # json
        if was_registered:
            return xcp_var

        symbol = self.symbols.get(variable, None)

        if symbol is None:
            raise UnknownSymbolError(variable)

        type_map = self.get_type_from_symbol(symbol)
        addr = symbol["addr"]

        xcp_var = XcpVar(
            name=variable, address=addr, size=type_map.size, data_type=type_map
        )
        self.selected_variables.append(xcp_var)

        return xcp_var

    def is_already_register(self, variable: str) -> Union[bool, XcpVar]:
        """Determine if a variable was already registered.

        :param variable: variable to seek for

        :return: if already exist True and the corresponding XcpVar
            instance otherwise False and None
        """

        for xcp_var in self.selected_variables:
            if xcp_var.name == variable:
                return True, xcp_var
        return False, None

    @staticmethod
    def get_type_from_symbol(symbol: dict) -> dict:
        """Return the variable/symbol type based on the definition inside
        the simplified A2L file.

        :param symbol: symbol definition (name ,enc,sz)

        :return: a mapping containing the use bytes order, the format
            for encoding/decoding and the size(in bytes)

        :raises InvalidSymbolTypeError: if the current type is not
            supported
        """
        data_type = None
        selected_map = None

        # gather symbol information
        symbol_type = symbol["enc"]
        symbol_size = symbol["sz"]
        is_unsigned = symbol_type == "UNSIGNED"
        is_real = symbol_type == "REAL"

        if is_real:
            selected_map = REAL_TYPE_MAP
        elif is_unsigned:
            selected_map = UNSIGNED_TYPE_MAP
        else:
            selected_map = SIGNED_TYPE_MAP

        for type_map in selected_map.values():
            if symbol_size == type_map.size:
                data_type = type_map
                break
        else:
            raise InvalidSymbolTypeError(symbol_type, symbol)
        return data_type

    def start_acquisition(self) -> None:
        """Start a acquisition by configuring the associated XCP
        channel with the corresponding DAQLists, ODT, and variables
        information (size, address)

        The following steps are performed :
            - allocate the number of DAQList
            - allocate the number of ODT
            - allocate the number of ODT entries per ODT
            - set the given DAQ ptr per variable information
            - associate each DAQList to the DAQ channel (1ms, 10ms...)
            - start the acquisition
        """
        self.master_xcp.freeDaq()

        self.create_acquisition_set()
        self.allocate_daq()
        self.allocate_odt()
        self.allocate_odt_entries()
        self.allocate_data_pointer()
        self.configure_daq_list()
        self.select_daq_list()

        self.master_xcp.startStopSynch(AcqCommands.START_SELECTED)

    def stop_acquisition(self) -> None:
        """Stop the current acquistion by stopping all running commands."""
        self.master_xcp.startStopSynch(AcqCommands.STOP_ALL)
        self.store_records()

    def store_records(self) -> None:
        """Dequeue all recorded values during the DAQ acquisition and
        store it in the corresponding ODT list.
        """
        max_values = len(self.master_xcp.transport.daqQueue)
        for _ in range(max_values):
            # data contain in the queue are as follow:
            # position 0 : raw bytes received
            # position 1 : message counter
            # position 2 : message length
            # position 3 : timestamp
            (
                raw_bytes,
                _,
                _,
                _,
            ) = self.master_xcp.transport.daqQueue.popleft()
            pid = raw_bytes[0]
            # pid byte is not part of the payload
            offset = 1
            for xcp_var in self.odt_set[pid]:
                xcp_var.add_record(raw_bytes[offset : offset + xcp_var.size])
                offset += xcp_var.size

    def create_acquisition_set(self) -> None:
        """Create the needed DAQ list and ODTs based on registered
        variables list. The output is a list representing all variables
        to record by event (1ms, 10ms, 100ms...).
        """
        count = 0
        for event, var_list in self.acq_register.items():
            if var_list:
                daq_list = DaqList(number=count, event=event)
                variables = daq_list.create_odts(var_list)
                self.acq_set.append(daq_list)
                self.odt_set.extend(variables)
                count += 1

    def allocate_daq(self) -> None:
        """Allocate the needed number of DAQ lists based on the
        registered values.
        """
        daq_count = len(self.acq_set)
        self.master_xcp.allocDaq(daq_count)

    def allocate_odt(self) -> None:
        """Allocate the number of needed ODTs based on the  registered
        values.
        """
        for daq_list in self.acq_set:
            odt_count = len(daq_list.odts)
            self.master_xcp.allocOdt(daq_list.number, odt_count)

    def allocate_odt_entries(self) -> None:
        """Alloacte an ODT entry for each registered variables, at the
        appropriate DAQ list and ODT number
        """
        for daq_list in self.acq_set:
            for odt in daq_list.odts:
                entries_count = len(odt.variables)
                self.master_xcp.allocOdtEntry(
                    daq_list.number, odt.number, entries_count
                )

    def allocate_data_pointer(self) -> None:
        """Allocate registered variables address and size to the slave
        ECU, for each ODT entries.
        """
        offset = PointerSettings.VAR_OFFSET
        ext = PointerSettings.EXT_ADDRESS

        for daq_list in self.acq_set:
            for odt in daq_list.odts:
                for entry_number, variable in enumerate(odt.variables):
                    self.master_xcp.setDaqPtr(daq_list.number, odt.number, entry_number)
                    self.master_xcp.writeDaq(
                        offset, variable.size, ext, variable.address
                    )

    def configure_daq_list(self) -> None:
        """Configure each DAQ list by linking each one to the
        corresponding DAQ event.
        """
        mode = DaqListSettings.MODE
        prescaler = DaqListSettings.PRESCALER
        priority = DaqListSettings.PRIORITY
        for daq_list in self.acq_set:
            self.master_xcp.setDaqListMode(
                mode, daq_list.number, daq_list.event, prescaler, priority
            )

    def select_daq_list(self) -> None:
        """Select the corresponding DAQList for the recording."""
        for daq_list in self.acq_set:
            self.master_xcp.startStopDaqList(StartStopDaqList.SELECT, daq_list.number)

    def read_variable(self, address: int, size: int) -> bytes:
        """Simply read the given variable (by it address and size) using
        XCP protocol.

        :param address: variable's address
        :param size: variable's size im bytes

        :return: raw response from the slave
        """
        self.master_xcp.setMta(address)
        payload_limit = max(size, XcpCanSettings.PAYLOAD_LIMIT)
        return self.master_xcp.fetch(size, payload_limit)

    def write_variable(self, address: int, value: bytes) -> None:
        """Symply write thegiven value at the corresponding variable
        address.

        :param address: variable's address
        :param value: value to write
        """
        self.master_xcp.setMta(address)
        self.master_xcp.push(value)
