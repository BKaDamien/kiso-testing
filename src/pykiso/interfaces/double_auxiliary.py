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
import sys

from typing import List, Optional, Any, Union, Tuple
from pykiso import CChannel, AuxiliaryInterface
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
        self.associat_tx_queue(self.queue_tx)

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
        stopped = self.run_command(cmd_message="stop")
        self.stop_rx.set()
        self.stop_tx.set()
        
        if not stopped:
            log.critical(f"Unexpected error occured during running stop command! {self.name}")
        log.info(f"stop auxiliary {self.name}")
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
                    response_received = self.used_queue.get(blocking, timeout_in_s)
                    log.debug(
                        f"reply to command '{cmd_message}' received: '{response_received}' in {self}"
                    )
                except queue.Empty:
                    log.error("no reply received within time")
                    response_received = None


            return response_received

    def _transmit_task(self):

        while not self.stop_tx.is_set():

            cmd, data = self.queue_in.get()

            if cmd == "stop":
                self.used_queue.put(True)
                break

            response = self._run_command(cmd, data)
            if response is not None:
                self.used_queue.put(response)

    def _reception_task(self):
        counter = 0
        while not self.stop_rx.is_set():
            recv_message = self._receive_message(timeout_in_s=1)
            # If yes, send it via the out queue
            counter = counter + 1
            if recv_message is not None:
                self.queue_out.put(recv_message)

        print(f"counter {counter} of {self.name}")

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

class ProxyAuxiliary(DoubleThreadAuxiliary):
    """Proxy auxiliary for multi auxiliaries communication handling."""

    def __init__(
        self,
        com: CChannel,
        aux_list: List[str],
        activate_trace: bool = False,
        trace_dir: Optional[str] = None,
        trace_name: Optional[str] = None,
        **kwargs,
    ):
        """Initialize attributes.

        :param com: Communication connector
        :param aux_list: list of auxiliary's alias
        """
        self.channel = com
        self.logger = ProxyAuxiliary._init_trace(activate_trace, trace_dir, trace_name)
        self.proxy_channels = self.get_proxy_con(aux_list)
        super().__init__(**kwargs)

    @staticmethod
    def _init_trace(
        activate: bool, t_dir: Optional[str] = None, t_name: Optional[str] = None
    ) -> logging.Logger:
        """Initialize the logging trace for proxy auxiliary received
        message recording.

        :param activate: True if the trace is activate otherwise False
        :param t_dir: trace directory path (absolute or relative)
        :param t_name: trace full name (without file extension)

        :return : created logger containing the configured
            FileHander otherwise default logger
        """
        logger = log

        if not activate:
            return logger

        # Just avoid the case the given trace directory is None
        t_dir = "" if t_dir is None else t_dir
        # if the given log path is not absolute add root path
        # (where pykiso is launched) otherwise take it as it is
        dir_path = (
            (Path() / t_dir).resolve() if not Path(t_dir).is_absolute() else Path(t_dir)
        )
        # if no specific logging file name is given take the default one
        t_name = (
            time.strftime(f"%Y-%m-%d_%H-%M-%S_{t_name}.log")
            if t_name is not None
            else time.strftime("%Y-%m-%d_%H-%M-%S_proxy_logging.log")
        )
        # if path doesn't exists take root path (where pykiso is launched)
        log_path = (
            dir_path / t_name if dir_path.exists() else (Path() / t_name).resolve()
        )

        # configure the file handler and create the trace file
        log_format = logging.Formatter("%(asctime)s : %(message)s")
        log.info(f"create proxy trace file at {log_path}")
        handler = logging.FileHandler(log_path, "w+")
        handler.setFormatter(log_format)
        # create logger and set the log level to DEBUG
        logger = logging.getLogger(f"{__name__}.PROXY")
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

        return logger

    def get_proxy_con(
        self, aux_list: List[Union[str]]
    ) -> Tuple:
        """Retrieve all connector associated to all given existing Auxiliaries.

        If auxiliary alias exists but auxiliary instance was not created
        yet, create it immediately using ConfigRegistry _aux_cache.

        :param aux_list: list of auxiliary's alias

        :return: tuple containing all connectors associated to
            all given auxiliaries
        """
        channel_inst = []

        for aux in aux_list:
            # aux_list can contain a auxiliary instance just grab the
            # channel
            if isinstance(aux, AuxiliaryInterface):
                self._check_compatibility(aux)
                channel_inst.append(aux.channel)
                continue
            # check the system module in order to get the auxiliary
            # instance
            aux_inst = sys.modules.get(f"{PACKAGE}.auxiliaries.{aux}")
            if aux_inst is not None:
                self._check_compatibility(aux_inst)
                channel_inst.append(aux_inst.channel)
            # check if the given aux_name is in the available aux
            # alias list
            elif aux in ConfigRegistry.get_auxes_alias():
                log.warning(
                    f"Auxiliary : {aux} is not using import magic mechanism (pre-loaded)"
                )
                # load it using ConfigRegistry _aux_cache
                aux_inst = ConfigRegistry._linker._aux_cache.get_instance(aux)
                self._check_compatibility(aux_inst)
                channel_inst.append(aux_inst.channel)
            # the given auxiliary alias doesn't exist or refer to a
            # invalid one
            else:
                log.error(f"Auxiliary : {aux} doesn't exist")

        return tuple(channel_inst)

    @staticmethod
    def _check_compatibility(aux) -> None:
        """Check if the given auxiliary is proxy compatible.

        :param aux: auxiliary instance to check

        :raises NotImplementedError: if is_proxy_capable flag is False
        """
        if not aux.is_proxy_capable:
            raise NotImplementedError(
                f"Auxiliary {aux} is not compatible with a proxy auxiliary"
            )

    def _create_auxiliary_instance(self) -> bool:
        """Open current associated channel.

        :return: if channel creation is successful return True otherwise false
        """
        try:
            log.info("Create auxiliary instance")
            log.info("Enable channel")
            self.channel.open()
            return True
        except Exception as e:
            log.exception(f"Error encouting during channel creation, reason : {e}")
            self.stop()
            return False

    def _delete_auxiliary_instance(self) -> bool:
        """Close current associated channel.

        :return: always True
        """
        try:
            log.info("Delete auxiliary instance")
            self.channel.close()
        except Exception as e:
            log.exception(f"Error encouting during channel closure, reason : {e}")
        finally:
            return True

    def _run_command(self) -> None:
        """Run all commands present in each proxy connectors queue in
        by sending it over current associated CChannel.

        In addition, all commands are dispatch to others auxiliaries
        using proxy connector queue out.
        """
        for conn in self.proxy_channels:
            if not conn.queue_in.empty():
                args, kwargs = conn.queue_in.get()
                message = kwargs.get("msg")
                if message is not None:
                    self._dispatch_command(
                        con_use=conn,
                        **kwargs,
                    )
                self.channel.cc_send(*args, **kwargs)

    def _dispatch_command(self, con_use: CChannel, **kwargs: dict):
        """Dispatch the current command to others connected auxiliaries.

        This action is performed by populating the queue out from each
        proxy connectors.

        :param con_use: current proxy connector where the command comes
            from
        :param kwargs: named arguments
        """
        for conn in self.proxy_channels:
            if conn != con_use:
                conn.queue_out.put(kwargs)

    def _abort_command(self) -> None:
        """Not Used."""
        return True

    def _receive_message(self, timeout_in_s: float = 0) -> None:
        """When no request are sent this method is called by AuxiliaryInterface run
        method. At each message received, this method will populate each
        proxy connectors queue out.

        :param timeout_in_s: maximum amount of time in second to wait
            for a message.
        """
        try:
            recv_response = self.channel.cc_receive(timeout=timeout_in_s, raw=True)
            received_data = recv_response.get("msg")
            # if data are received, populate connected proxy connectors
            # queue out
            if received_data is not None:
                self.logger.debug(
                    f"received response : data {received_data.hex()} || channel : {self.channel.name}"
                )
                for conn in self.proxy_channels:
                    conn.queue_out.put(recv_response)
        except Exception:
            log.exception(
                f"encountered error while receiving message via {self.channel}"
            )

    def run_command(
            self,
            cmd_message: MsgType,
            cmd_data: Any = None,
            blocking: bool = True,
            timeout_in_s: int = 5,
        ) -> bool:
        return True

    def _transmit_task(self):

        while not self.stop_tx.is_set():

            time.sleep(0.001)
            self._run_command()
