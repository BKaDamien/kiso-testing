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
:module: xcp_auxiliary

:synopsis: auxiliary used to handle xcp protocol.

.. currentmodule:: xcp_auxiliary
"""

import json
import logging
from typing import Any

from pykiso import CChannel, SimpleAuxiliaryInterface
from pyxcp.master import Master
from pyxcp.master.errorhandler import disable_error_handling
from pya2l import DB

from .utils import AcqTasks
from .xcp_daq import Daq

log = logging.getLogger(__name__)


class XcpAuxiliary(SimpleAuxiliaryInterface):
    """Enable XCP communication for ECU internal variables recording,
    reading and writing.
    """

    def __init__(
        self, com: CChannel, com_config: str, symbols_config: str, **kwargs
    ) -> None:
        """Initialize attributes.

        :param com: communication channel connector
        :param com_config: path to communication interface settings
            (json format), only used for pyxcp
        :param symbols_config: path to the simplified A2L file
            (json format)
        """
        self.is_proxy_capable = True
        super().__init__(**kwargs)
        self.channel = com
        self.adapter = None
        self.com_config = self.open_json(com_config)
        # self.symbols_config = self.open_json(symbols_config)
        self.symbols_a2l= DB().import_a2l(symbols_config)
        print("wadwadwadwadwadwadwad")
        print(type(self.symbols_a2l))
        self.daq = None
        self.master_xcp = None
        self.transport_type = self.com_config["TRANSPORT"].lower()

    @staticmethod
    def open_json(path: str) -> dict:
        """Open a json file and return its content.

        :param path: json file full path

        :return: json file content
        """
        log.info(f"Load content from {path} file")
        with open(path, "r") as file:
            content = json.load(file)
        return content

    def _create_auxiliary_instance(self) -> bool:
        """Open current associated channel.

        :return: if channel creation is successful return True otherwise
            false
        """
        log.info("Create auxiliary instance")
        log.info("Enable channel")

        try:
            self.channel.open()
        except Exception:
            log.exception("Error encountered during channel creation.")
            return False
        return True

    def _delete_auxiliary_instance(self) -> bool:
        """Close current associated channel and close XCP communication.

        :return: always True
        """
        log.info("Delete auxiliary instance")
        try:
            # if adapter is None the pyxcp doesn't open the listener
            # so no need to close it
            if self.adapter is not None:
                if self.adapter.parent.listener.is_alive():
                    self.daq.close()
                    self.adapter.close()
            self.channel.close()
        except Exception:
            log.exception("Unable to close Channel.")
        return True

    def connect(self) -> None:
        """Establish the connection with the slave(DUT) and init DAQ
        instance.
        """
        log.info("Connect the master to the slave")
        self.master_xcp = Master(self.transport_type, config=self.com_config)
        self.master_xcp.transport.canInterface.associate_channel(self.channel)
        self.adapter = self.master_xcp.transport.canInterface
        self.daq = Daq(self.symbols_config, self.master_xcp)
        # disable the pyxcp error handling mechanism otherwise possible
        # issues could be seen on communication error (infinite loop)
        disable_error_handling(True)
        self.daq.open()

    def disconnect(self) -> None:
        """Disconnect the master(PC) from the slave(DUT), and close all
        kind of existing communication (listener thread, connector...).
        """
        log.info("Disconnect the master from the slave")
        if self.adapter is not None:
            if self.adapter.parent.listener.is_alive():
                self.daq.close()
                self.adapter.close()

    def register_1ms_variable(self, variable: str) -> None:
        """Register a variable to the DAQ 1ms event.

        :param variable: variable's name
        """
        log.info(f"register symbol {variable} to 1ms event")
        return self.daq.register_variable(variable, AcqTasks.ONE_MS)

    def register_10ms_variable(self, variable: str) -> None:
        """Register a variable to the DAQ 10ms event.

        :param variable: variable's name
        """
        log.info(f"register symbol {variable} to 10ms event")
        return self.daq.register_variable(variable, AcqTasks.TEN_MS)

    def register_100ms_variable(self, variable: str) -> None:
        """Register a variable to the DAQ 100ms event.

        :param variable: variable's name
        """
        log.info(f"register symbol {variable} to 100ms event")
        return self.daq.register_variable(variable, AcqTasks.HUNDRED_MS)

    def register_500ms_variable(self, variable: str) -> None:
        """Register a variable to the DAQ 500ms event.

        :param variable: variable's name
        """
        log.info(f"register symbol {variable} to 500ms event")
        return self.daq.register_variable(variable, AcqTasks.FIVE_HUNDRED_MS)

    def start_acquisition(self) -> None:
        """Start xcp daq acquisition using pre-configured."""
        log.info("Start DAQ acquisition")
        self.daq.start_acquisition()

    def stop_acquisition(self) -> None:
        """Stop all current daq acquisitions."""
        log.info("Stop DAQ acquisition")
        self.daq.stop_acquisition()

    def reset_acquisition(self) -> None:
        """Reset all registered variable and all used containers."""
        log.info("Reset DAQ configuration and resources")
        self.daq.reset_acquisition_ressources()

    def reset_acquired_records(self) -> None:
        """Reset all acquired records for all referenced variables."""
        log.info("Reset all acquired records")
        self.daq.reset_records()

    def read_variable(self, variable: str) -> Any:
        """Read a variable from slave based on it address and size

        :param variable: variable's full name

        :return: the converted value based on variable type
            (float, int,...)
        """
        xcp_var = self.daq.select_variable(variable)
        log.info(f"Read variable {xcp_var.name} at {hex(xcp_var.address)}")
        raw_value = self.daq.read_variable(xcp_var.address, xcp_var.data_type.size)
        xcp_var.snapshot_value = xcp_var.from_bytes(raw_value)
        return xcp_var.snapshot_value

    def write_variable(self, variable: str, value: Any) -> None:
        """Write the given value at the defined variable address.

        :param variable: variable's full name
        :param value: value to write
        """
        xcp_var = self.daq.select_variable(variable)
        log.info(
            f"Write value {value} to variable {xcp_var.name} at {hex(xcp_var.address)}"
        )
        bytes_value = xcp_var.to_bytes(value)
        self.daq.write_variable(xcp_var.address, bytes_value)
