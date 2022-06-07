##########################################################################
# Copyright (c) 2010-2022 Robert Bosch GmbH
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# http://www.eclipse.org/legal/epl-2.0.
#
# SPDX-License-Identifier: EPL-2.0
##########################################################################
import abc
import logging
import threading
import queue
import time

from typing import List, Optional, Any
from pykiso import CChannel
from pykiso.test_setup.dynamic_loader import PACKAGE

#from pykiso import Records
from ..exceptions import AuxiliaryCreationError
from ..types import MsgType

log = logging.getLogger(__name__)


class DoubleThreadAuxiliary:

    def __init__(self, name : str = None, auto_start: bool = True, activate_log: List[str] = None, is_proxy_capable=False) -> None:
        self.name = name
        self.is_proxy_capable = is_proxy_capable
        self.initialize_loggers(activate_log)
        self.lock = threading.RLock()
        self.stop_tx = threading.Event()
        self.stop_rx = threading.Event()
        self.queue_in = queue.Queue()
        self.queue_tx = queue.Queue()
        self.queue_out = queue.Queue()
        self.is_instance = False

    @staticmethod
    def initialize_loggers(loggers: Optional[List[str]]) -> None:
        """Deactivate all external loggers except the specified ones.

        :param loggers: list of logger names to keep activated
        """
        if loggers is None:
            loggers = list()
        # keyword 'all' should keep all loggers to the configured level
        if "all" in loggers:
            log.warning(
                "All loggers are activated, this could lead to performance issues."
            )
            return
        # keep package and auxiliary loggers
        relevant_loggers = {
            name: logger
            for name, logger in logging.root.manager.loggerDict.items()
            if not (name.startswith(PACKAGE) or name.endswith("auxiliary"))
            and not isinstance(logger, logging.PlaceHolder)
        }
        # keep child loggers
        childs = [
            logger
            for logger in relevant_loggers.keys()
            for parent in loggers
            if (logger.startswith(parent) or parent.startswith(logger))
        ]
        loggers += childs
        # keep original level for specified loggers
        loggers_to_deactivate = set(relevant_loggers) - set(loggers)
        for logger_name in loggers_to_deactivate:
            logging.getLogger(logger_name).setLevel(logging.WARNING)

    def create_instance(self) -> bool:
        with self.lock:
            created = self._create_auxiliary_instance()

            if not created:
                raise AuxiliaryCreationError(self.name)

            self.tx_thread = threading.Thread(target=self._transmit_task)
            self.rx_thread = threading.Thread(target=self._reception_task)
            self.rx_thread.start()
            self.tx_thread.start()
            self.is_instance = True

            return created

    def delete_instance(self) -> bool:
        with self.lock:
            deleted = self._delete_auxiliary_instance()

            if not deleted:
                log.error("Unexpected error occured during auxiliary instance deletion")
            self.is_instance = False
            return deleted

    def stop(self):
        self.stop_rx.set()
        self.stop_tx.set()
        stopped = self.run_command(cmd_message="stop")

        if not stopped:
            log.critical("Unexpected error occured during running stop command!")

        self.rx_thread.join()
        self.tx_thread.join()

    def associat_tx_queue(self, queue):
        self.used_queue = queue 

    def run_command(
            self,
            cmd_message: MsgType,
            cmd_data: Any = None,
            blocking: bool = True,
            timeout_in_s: int = 5,
        ) -> bool:

            with self.lock:
                self.queue_in.put((cmd_message, cmd_data))

                try:
                    response_received = self.queue_out.get(blocking, timeout_in_s)
                    log.info(
                        f"reply to command '{cmd_message}' received: '{response_received}' in {self}"
                    )
                except queue.Empty:
                    log.error("no reply received within time")


            return response_received

    def _transmit_task(self):

        while not self.stop_tx.is_set():

            cmd, data = self.queue_in.get()

            if cmd == "stop":
                self.queue_out.put(True)
                break

            response = self._run_command(cmd, data)
            if response is not None:
                self.queue_out.put(response)

    def _reception_task(self):

        while not self.stop_rx.is_set():
            recv_message = self._receive_message(timeout_in_s=1)
            # If yes, send it via the out queue
            if recv_message is not None:
                self.queue_out.put(recv_message)

    def wait_and_get_report(
        self, blocking: bool = False, timeout_in_s: int = 0
    ) -> MsgType:
        """Wait for the report of the previous sent test request.

        :param blocking: True: wait for timeout to expire, False: return immediately
        :param timeout_in_s: if blocking, wait the defined time in seconds

        :return: a message.Message() - Message received / None - nothing received
        """
        try:
            return self.queue_out.get(blocking, timeout_in_s)
        except queue.Empty:
            return None

    @abc.abstractmethod
    def _create_auxiliary_instance(self) -> bool:
        """Create the auxiliary instance with witch we will communicate.

        :return: True - Successfully created / False - Failed by creation

        .. note: Errors should be logged via the logging with the right level
        """
        pass

    @abc.abstractmethod
    def _delete_auxiliary_instance(self) -> bool:
        """Delete the auxiliary instance with witch we will communicate.

        :return: True - Successfully deleted / False - Failed deleting

        .. note: Errors should be logged via the logging with the right level
        """
        pass

    @abc.abstractmethod
    def _run_command(self, cmd_message: MsgType, cmd_data: bytes = None) -> MsgType:
        """Run a command for the auxiliary.

        :param cmd_message: command in form of a message to run

        :param cmd_data: payload data for the command

        :return: True - Successfully received by the instance / False - Failed sending

        .. note: Errors should be logged via the logging with the right level
        """
        pass
    @abc.abstractmethod
    def _receive_message(self, timeout_in_s: float) -> MsgType:
        """Defines what needs to be done as a receive message. Such as,
            what do I need to do to receive a message.

        :param timeout_in_s: How much time to block on the receive

        :return: message.Message - If one received / None - Else
        """
        pass


class ComAux(DoubleThreadAuxiliary):

    def __init__(self, com: CChannel, **kwargs):
        """Constructor.

        :param com: CChannel that supports raw communication
        """
        super().__init__(is_proxy_capable=True, **kwargs)
        self.channel = com

    def send_message(self, raw_msg: bytes) -> bool:
        """Send a raw message (bytes) via the communication channel.

        :param raw_msg: message to send

        :return: True if command was executed otherwise False
        """
        return self.run_command("send", raw_msg, timeout_in_s=5)


    def receive_message(
        self, blocking: bool = True, timeout_in_s: float = None
    ) -> Optional[bytes]:
        """Receive a raw message.

        :param blocking: wait for message till timeout elapses?
        :param timeout_in_s: maximum time in second to wait for a response

        :returns: raw message
        """
        log.debug(
            f"retrieving message in {self} (blocking={blocking}, timeout={timeout_in_s})"
        )
        response = self.wait_and_get_report(
            blocking=blocking, timeout_in_s=timeout_in_s
        )
        log.debug(f"retrieved message '{response}' in {self}")

        # if queue.Empty exception is raised None is returned so just
        # directly return it
        if response is None:
            return None

        msg = response.get("msg")
        remote_id = response.get("remote_id")

        # stay with the old return type to not making a breaking change
        if remote_id is not None:
            return (msg, remote_id)
        return msg

    def _create_auxiliary_instance(self) -> bool:
        """Open the connector communication.

        :return: always True
        """
        state = False
        log.info("Create auxiliary instance")
        log.info("Enable channel")
        self.associat_tx_queue(self.queue_tx)
        try:
            self.channel.open()
            state = True
        except Exception:
            log.exception("Unable to open channel communication")
            self.stop()
        return state

    def _delete_auxiliary_instance(self) -> bool:
        """Close the connector communication.

        :return: always True
        """
        log.info("Delete auxiliary instance")
        try:
            self.channel.close()
        except Exception:
            log.exception("Unable to close channel communication")
        return True


    def _receive_message(self, timeout_in_s: float) -> bytes:
        """No-op since it's handled in _run_command

        :param timeout_in_s: not used

        :return: received message
        """
        try:
            rcv_data = self.channel.cc_receive(timeout=timeout_in_s, raw=True)
            msg = rcv_data.get("msg")
            if msg is not None:
                log.debug(f"received message '{rcv_data}' from {self.channel}")
                return rcv_data
        except Exception:
            log.exception(
                f"encountered error while receiving message via {self.channel}"
            )
            return None

    def _run_command(self, cmd_message: bytes, cmd_data: bytes = None) -> bool:
        """Run the corresponding command.

        :param cmd_message: command type
        :param cmd_data: payload data to send over CChannel

        :return: True if command is executed otherwise False
        """
        if cmd_message == "send":
            try:
                self.channel.cc_send(msg=cmd_data, raw=True)
                return True
            except Exception:
                log.exception(
                    f"encountered error while sending message '{cmd_data}' to {self.channel}"
                )
        # elif isinstance(cmd_message, Message):
        #     log.debug(f"ignored command '{cmd_message} in {self}'")
        #     return True
        else:
            log.warning(f"received unknown command '{cmd_message} in {self}'")
        return False
