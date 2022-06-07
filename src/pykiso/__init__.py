##########################################################################
# Copyright (c) 2010-2022 Robert Bosch GmbH
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# http://www.eclipse.org/legal/epl-2.0.
#
# SPDX-License-Identifier: EPL-2.0
##########################################################################

"""
pykiso - extensible framework for (embedded) integration testing.
*****************************************************************

:module: pykiso

:synopsis: ``pykiso`` is an extensible framework for (embedded) integration testing.

.. currentmodule:: pykiso

"""

import pkg_resources

__version__ = pkg_resources.get_distribution(__package__).version


from . import auxiliary, cli, config_parser, connector, message, types
from .auxiliary import AuxiliaryCommon
from .connector import CChannel, Flasher
from .interfaces.mp_auxiliary import MpAuxiliaryInterface
from .interfaces.simple_auxiliary import SimpleAuxiliaryInterface
from .interfaces.thread_auxiliary import AuxiliaryInterface
from .interfaces.double_auxiliary import DoubleThreadAuxiliary
from .message import Message
from .test_coordinator import test_case, test_message_handler, test_suite
from .test_coordinator.test_case import (
    BasicTest,
    define_test_parameters,
    retry_test_case,
)
from .test_coordinator.test_suite import (
    BasicTestSuiteSetup,
    BasicTestSuiteTeardown,
)


import functools
import time
import logging
from dataclasses import dataclass
import psutil
import os

@dataclass
class Rec:

    obj: str
    func : str
    start : float
    stop : float = None
    elapse : float = None

class Records:

    stats = {}

    def execution_time(func):

        @functools.wraps(func)
        def record_inner(self, *args, **kwargs):
            f_name = func.__name__
            record = Rec(type(self).__name__, f_name, time.perf_counter())
            ret = func(self, *args, **kwargs)
            record.stop = time.perf_counter()
            record.elapse = record.stop - record.start

            if Records.stats.get(f_name) is None:
                Records.stats[f_name] = []

            Records.stats[f_name].append(record)
            return ret
        return record_inner


    def write_records():
        
        for func, record in Records.stats.items():
            with open(f"records_{func}.csv", "w+") as file:
                for idx, rec in enumerate(record):
                    file.write(f"{idx};{rec.obj};{rec.func};{str(float(float(rec.elapse) * 1000)).replace('.', ',')};ms \n")

