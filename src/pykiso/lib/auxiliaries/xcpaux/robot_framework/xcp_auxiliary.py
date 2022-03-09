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
XCP Auxiliary plugin
********************

:module: xcp_auxiliary

:synopsis: implementation of existing XcpAuxiliary for Robot
    framework usage.

.. currentmodule:: xcp_auxiliary

"""

from typing import Any

from pykiso.lib.robot_framework.aux_interface import RobotAuxInterface
from robot.api.deco import keyword, library

from ..xcp_auxiliary import XcpAuxiliary as XcpAux
from ..xcp_daq import XcpVar


@library(version="0.1.0")
class XcpAuxiliary(RobotAuxInterface):
    """Robot framework plugin for UdsAuxiliary."""

    ROBOT_LIBRARY_SCOPE = "SUITE"

    def __init__(self):
        """Initialize attributes."""
        super().__init__(aux_type=XcpAux)

    @keyword(name="Register 1ms variable")
    def register_1ms_variable(self, variable: str, aux_alias: str) -> XcpVar:
        """Register a variable to the DAQ 1ms event.

        :param variable: variable's name
        :param aux_alias: auxiliary's alias
        """
        aux = self._get_aux(aux_alias)
        return aux.register_1ms_variable(variable)

    @keyword(name="Register 10ms variable")
    def register_10ms_variable(self, variable: str, aux_alias: str) -> XcpVar:
        """Register a variable to the DAQ 10ms event.

        :param variable: variable's name
        :param aux_alias: auxiliary's alias
        """
        aux = self._get_aux(aux_alias)
        return aux.register_10ms_variable(variable)

    @keyword(name="Register 100ms variable")
    def register_100ms_variable(self, variable: str, aux_alias: str) -> XcpVar:
        """Register a variable to the DAQ 100ms event.

        :param variable: variable's name
        :param aux_alias: auxiliary's alias
        """
        aux = self._get_aux(aux_alias)
        return aux.register_100ms_variable(variable)

    @keyword(name="Register 500ms variable")
    def register_500ms_variable(self, variable: str, aux_alias: str) -> XcpVar:
        """Register a variable to the DAQ 500ms event.

        :param variable: variable's name
        :param aux_alias: auxiliary's alias
        """
        aux = self._get_aux(aux_alias)
        return aux.register_500ms_variable(variable)

    @keyword(name="Start acquisition")
    def start_acquisition(self, aux_alias: str) -> None:
        """Start xcp daq acquisition using pre-configured.

        :param aux_alias: auxiliary's alias
        """
        aux = self._get_aux(aux_alias)
        aux.start_acquisition()

    @keyword(name="Stop acquisition")
    def stop_acquisition(self, aux_alias: str) -> None:
        """Stop all current daq acquisitions.

        :param aux_alias: auxiliary's alias
        """
        aux = self._get_aux(aux_alias)
        aux.stop_acquisition()

    @keyword(name="Reset acquisition")
    def reset_acquisition(self, aux_alias: str) -> None:
        """Reset all registered variable and all used containers.

        :param aux_alias: auxiliary's alias
        """
        aux = self._get_aux(aux_alias)
        aux.reset_acquisition()

    @keyword(name="Reset acquired records")
    def reset_acquired_records(self, aux_alias: str) -> None:
        """Reset all acquired records for all referenced variables.

        :param aux_alias: auxiliary's alias
        """
        aux = self._get_aux(aux_alias)
        aux.reset_acquired_records()

    @keyword(name="Read variable")
    def read_variable(self, variable: str, aux_alias: str) -> Any:
        """Read a variable from slave based on it address and size

        :param variable: variable's full name
        :param aux_alias: auxiliary's alias

        :return: the converted value based on variable type
            (float, int,...)
        """
        aux = self._get_aux(aux_alias)
        return aux.read_variable(variable)

    @keyword(name="Write variable")
    def write_variable(self, variable: str, value: Any, aux_alias: str) -> None:
        """Write the given value at the defined variable address.

        :param variable: variable's full name
        :param value: value to write
        :param aux_alias: auxiliary's alias
        """
        aux = self._get_aux(aux_alias)
        aux.write_variable(variable, value)
