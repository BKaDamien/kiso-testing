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
:module: xcp_adapter

:synopsis: Encapsulate all communication adapters in order to correctly
    link ITF's connector implementation and pyxcp communication
    mechanism.

.. currentmodule:: xcp_adapter
"""


import time
from typing import Callable

from pykiso import CChannel
from pyxcp.master import Master
from pyxcp.transport.can import CanInterfaceBase, Frame


class CanAdapter(CanInterfaceBase):
    """Based on CanInterfaceBase abstract class, this class is
    responsible to adapt the reception and the transmission for pyxcp.
    """

    def init(self, parent: Master, receive_callback: Callable) -> None:
        """Initialize attributes.

        :param parent: pyxcp's master instance
        :param receive_callback: function use as callback for listener
            thread
        """
        self.parent = parent
        self.receive_callback = receive_callback
        self.channel = None

    def connect(self) -> None:
        """Not used, connection managed by ITF on connector level."""
        pass

    def close(self) -> None:
        """Stop the pyxcp listener thread."""
        self.parent.finishListener()
        if self.parent.listener.is_alive():
            self.parent.listener.join()

    def getTimestampResolution(self) -> int:
        """Return the timestamp resolution in use, but useful for pyxcp.

        :return: current timestamp resolution
        """
        return 1000 * 1000 * 1000

    def is_fd(self) -> bool:
        """Not used by ITF but used by pyxcp for padding management.

        :return: force to True
        """
        return True

    def read(self) -> Frame:
        """Read a CAN message through ITF's connector and transfer it
        to pyxcp by converting it to Frame instance.
        """
        msg, source = self.channel._cc_receive(timeout=1, raw=True)
        if msg is None or source != self.parent.can_id_master.id:
            return None
        return Frame(id_=source, dlc=len(msg), data=msg, timestamp=time.time())

    def transmit(self, payload: bytes) -> None:
        """Transmit the given payload from pyxcp to ITF's connector.

        :param payload: payload to send over CAN
        """
        self.channel._cc_send(
            msg=payload, remote_id=self.parent.can_id_slave.id, raw=True
        )

    def associate_channel(self, channel: CChannel) -> None:
        """Associate the ITF's CAN connector with the pyxcp adapter.

        :param channel: ITF's CAN connector
        """
        self.channel = channel
