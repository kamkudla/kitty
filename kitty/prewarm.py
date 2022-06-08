#!/usr/bin/env python
# License: GPLv3 Copyright: 2022, Kovid Goyal <kovid at kovidgoyal.net>

import io
import json
import os
import select
import sys
import time
import warnings
from contextlib import suppress
from dataclasses import dataclass
from importlib import import_module
from itertools import count
from typing import (
    IO, TYPE_CHECKING, Any, Dict, List, NoReturn, Optional, Sequence, Tuple,
    Union, cast
)

from kitty.constants import clear_handled_signals, kitty_exe
from kitty.entry_points import main as main_entry_point
from kitty.fast_data_types import (
    establish_controlling_tty, get_options, safe_pipe
)
from kitty.shm import SharedMemory

if TYPE_CHECKING:
    from _typeshed import ReadableBuffer, WriteableBuffer


error_events = select.POLLERR | select.POLLNVAL | select.POLLHUP


class PrewarmProcessFailed(Exception):
    pass


@dataclass
class Child:
    child_id: int
    child_process_pid: int


class PrewarmProcess:

    def __init__(self, create_file_to_read_from_worker: bool = False) -> None:
        self.from_worker_fd, self.in_worker_fd = safe_pipe()
        self.children: Dict[int, Child] = {}
        if create_file_to_read_from_worker:
            os.set_blocking(self.from_worker_fd, True)
            self.from_worker = open(self.from_worker_fd, mode='r', closefd=True)
            self.from_worker_fd = -1

    def take_from_worker_fd(self) -> int:
        ans, self.from_worker_fd = self.from_worker_fd, -1
        return ans

    def __del__(self) -> None:
        if self.from_worker_fd > -1:
            os.close(self.from_worker_fd)
            self.from_worker_fd = -1
        if hasattr(self, 'from_worker'):
            self.from_worker.close()
            del self.from_worker
        if self.worker_started:
            import subprocess
            self.process.stdin and self.process.stdin.close()
            self.process.stdout and self.process.stdout.close()
            try:
                self.process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                self.process.kill()
            del self.process

    @property
    def worker_started(self) -> bool:
        return self.in_worker_fd == -1

    @property
    def prewarm_config(self) -> str:
        opts = get_options()
        return json.dumps({'paths': opts.config_paths, 'overrides': opts.config_overrides})

    def is_prewarmed_argv(self, argv: Sequence[str]) -> bool:
        if argv[:2] != [kitty_exe(), '+runpy']:
            return False
        return len(argv) > 2 and argv[2].startswith('from kitty.prewarm import main; main(')

    def ensure_worker(self) -> None:
        if not self.worker_started:
            import subprocess
            env = dict(os.environ)
            env['KITTY_PREWARM_CONFIG'] = self.prewarm_config
            self.process = subprocess.Popen(
                [kitty_exe(), '+runpy', f'from kitty.prewarm import main; main({self.in_worker_fd})'],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, pass_fds=(self.in_worker_fd,), env=env,
                start_new_session=True, preexec_fn=clear_handled_signals)
            os.close(self.in_worker_fd)
            self.in_worker_fd = -1
            assert self.process.stdin is not None and self.process.stdout is not None
            self.write_to_process_fd = self.process.stdin.fileno()
            self.read_from_process_fd = self.process.stdout.fileno()
            os.set_blocking(self.write_to_process_fd, False)
            os.set_blocking(self.read_from_process_fd, False)
            self.poll = select.poll()
            self.poll.register(self.process.stdout.fileno(), select.POLLIN)

    def poll_to_send(self, yes: bool = True) -> None:
        if yes:
            self.poll.register(self.write_to_process_fd, select.POLLOUT)
        else:
            self.poll.unregister(self.write_to_process_fd)

    def reload_kitty_config(self) -> None:
        if self.worker_started:
            self.send_to_prewarm_process('reload_kitty_config:{self.prewarm_config}\n')

    def __call__(
        self,
        tty_fd: int,
        argv: List[str],
        cwd: str = '',
        env: Optional[Dict[str, str]] = None,
        stdin_data: Optional[Union[str, bytes]] = None
    ) -> Child:
        self.ensure_worker()
        tty_name = os.ttyname(tty_fd)
        if isinstance(stdin_data, str):
            stdin_data = stdin_data.encode()
        if env is None:
            env = dict(os.environ)
        cmd: Dict[str, Union[int, List[str], str, Dict[str, str]]] = {
            'tty_name': tty_name, 'cwd': cwd or os.getcwd(), 'argv': argv, 'env': env,
        }
        total_size = 0
        if stdin_data is not None:
            cmd['stdin_size'] = len(stdin_data)
            total_size += len(stdin_data)
        data = json.dumps(cmd).encode()
        total_size += len(data) + SharedMemory.num_bytes_for_size
        with SharedMemory(size=total_size, unlink_on_exit=True) as shm:
            shm.write_data_with_size(data)
            if stdin_data:
                shm.write(stdin_data)
            shm.flush()
            self.send_to_prewarm_process(f'fork:{shm.name}\n')
            input_buf = b''
            st = time.monotonic()
            while time.monotonic() - st < 2:
                for (fd, event) in self.poll.poll(0.2):
                    if event & error_events:
                        raise PrewarmProcessFailed('Failed doing I/O with prewarm process')
                    if fd == self.read_from_process_fd and event & select.POLLIN:
                        d = os.read(self.read_from_process_fd, io.DEFAULT_BUFFER_SIZE)
                        input_buf += d
                        while (idx := input_buf.find(b'\n')) > -1:
                            line = input_buf[:idx].decode()
                            input_buf = input_buf[idx+1:]
                            if line.startswith('CHILD:'):
                                _, cid, pid = line.split(':')
                                child = self.add_child(int(cid), int(pid))
                                shm.unlink_on_exit = False
                                return child
                            if line.startswith('ERR:'):
                                raise PrewarmProcessFailed(line.split(':', 1)[-1])
        raise PrewarmProcessFailed('Timed out waiting for I/O with prewarm process')

    def add_child(self, child_id: int, pid: int) -> Child:
        self.children[child_id] = c = Child(child_id, pid)
        return c

    def send_to_prewarm_process(self, output_buf: Union[str, bytes] = b'', timeout: float = 2) -> None:
        if isinstance(output_buf, str):
            output_buf = output_buf.encode()
        st = time.monotonic()
        while time.monotonic() - st < timeout and output_buf:
            self.poll_to_send(bool(output_buf))
            for (fd, event) in self.poll.poll(0.2):
                if event & error_events:
                    raise PrewarmProcessFailed('Failed doing I/O with prewarm process: {event}')
                if fd == self.write_to_process_fd and event & select.POLLOUT:
                    n = os.write(self.write_to_process_fd, output_buf)
                    output_buf = output_buf[n:]
        self.poll_to_send(False)
        if output_buf:
            raise PrewarmProcessFailed('Timed out waiting to write to prewarm process')

    def mark_child_as_ready(self, child_id: int) -> bool:
        c = self.children.pop(child_id, None)
        if c is None:
            return False
        self.send_to_prewarm_process(f'ready:{child_id}\n')
        return True


def reload_kitty_config() -> None:
    d = json.loads(os.environ.pop('KITTY_PREWARM_CONFIG'))
    from kittens.tui.utils import set_kitty_opts
    set_kitty_opts(paths=d['paths'], overrides=d['overrides'])


def prewarm() -> None:
    reload_kitty_config()
    from kittens.runner import all_kitten_names
    for kitten in all_kitten_names():
        with suppress(Exception):
            import_module(f'kittens.{kitten}.main')
    import_module('kitty.complete')


class MemoryViewReadWrapperBytes(io.BufferedIOBase):

    def __init__(self, mw: memoryview):
        self.mw = mw
        self.pos = 0

    def detach(self) -> io.RawIOBase:
        raise io.UnsupportedOperation('detach() not supported')

    def read(self, size: Optional[int] = -1) -> bytes:
        if size is None or size < 0:
            size = max(0, len(self.mw) - self.pos)
        oldpos = self.pos
        self.pos = min(len(self.mw), self.pos + size)
        if self.pos <= oldpos:
            return b''
        return bytes(self.mw[oldpos:self.pos])

    def readinto(self, b: 'WriteableBuffer') -> int:
        if not isinstance(b, memoryview):
            b = memoryview(b)
        b = b.cast('B')
        data = self.read(len(b))
        n = len(data)
        b[:n] = data
        return n
    readinto1 = readinto

    def readall(self) -> bytes:
        return self.read()

    def write(self, b: 'ReadableBuffer') -> int:
        raise io.UnsupportedOperation('readonly stream')

    def readable(self) -> bool:
        return True


class MemoryViewReadWrapper(io.TextIOWrapper):

    def __init__(self, mw: memoryview):
        super().__init__(cast(IO[bytes], MemoryViewReadWrapperBytes(mw)), encoding='utf-8', errors='replace')


def child_main(cmd: Dict[str, Any], ready_fd: int) -> NoReturn:
    cwd = cmd.get('cwd')
    if cwd:
        with suppress(OSError):
            os.chdir(cwd)
    env = cmd.get('env')
    if env is not None:
        os.environ.clear()
        os.environ.update(env)
    argv = cmd.get('argv')
    if argv:
        sys.argv = list(argv)
    poll = select.poll()
    poll.register(ready_fd, select.POLLIN | select.POLLERR | select.POLLHUP)
    tuple(poll.poll())
    os.close(ready_fd)
    main_entry_point()
    raise SystemExit(0)


def fork(shm_address: str, ready_fd: int) -> Tuple[int, int]:
    sz = pos = 0
    with SharedMemory(name=shm_address, unlink_on_exit=True) as shm:
        data = shm.read_data_with_size()
        cmd = json.loads(data)
        sz = cmd.get('stdin_size', 0)
        if sz:
            pos = shm.tell()
            shm.unlink_on_exit = False

    r, w = os.pipe()
    os.set_inheritable(r, False)
    try:
        child_pid = os.fork()
    except OSError:
        if sz:
            with SharedMemory(shm_address, unlink_on_exit=True):
                pass
    if child_pid:
        # master process
        os.close(w)
        poll = select.poll()
        poll.register(r, select.POLLIN)
        for (fd, event) in poll.poll():
            if event & select.POLLIN:
                os.read(r, 1)
                return child_pid, r
            else:
                raise ValueError('Child process pipe failed')
    # child process
    os.set_inheritable(w, False)
    os.setsid()
    tty_name = cmd.get('tty_name')
    if tty_name:
        sys.__stdout__.flush()
        sys.__stderr__.flush()
        establish_controlling_tty(tty_name, sys.__stdin__.fileno(), sys.__stdout__.fileno(), sys.__stderr__.fileno())
    os.write(w, b'1')  # this will be closed on process exit and thereby used to detect child death
    if shm.unlink_on_exit:
        child_main(cmd, ready_fd)
    else:
        with SharedMemory(shm_address, unlink_on_exit=True) as shm:
            stdin_data = memoryview(shm.mmap)[pos:pos + sz]
            if stdin_data:
                sys.stdin = MemoryViewReadWrapper(stdin_data)
            try:
                child_main(cmd, ready_fd)
            finally:
                stdin_data.release()
                sys.stdin = sys.__stdin__


def main(notify_child_death_fd: int) -> None:
    os.set_blocking(notify_child_death_fd, False)
    prewarm()
    stdin_fd = sys.__stdin__.fileno()
    os.set_blocking(stdin_fd, False)
    stdout_fd = sys.__stdout__.fileno()
    os.set_blocking(stdout_fd, False)
    poll = select.poll()
    poll.register(stdin_fd, select.POLLIN)
    input_buf = output_buf = child_death_buf = b''
    child_ready_fds: Dict[int, int] = {}
    child_death_fds: Dict[int, int] = {}
    child_id_map: Dict[int, int] = {}
    child_id_counter = count()
    self_pid = os.getpid()
    # runpy issues a warning when running modules that have already been
    # imported. Ignore it.
    warnings.filterwarnings('ignore', category=RuntimeWarning, module='runpy')

    def check_event(event: int, err_msg: str) -> None:
        if event & select.POLLHUP:
            raise SystemExit(0)
        if event & error_events:
            raise SystemExit(err_msg)

    def handle_input(event: int) -> None:
        nonlocal input_buf, output_buf
        check_event(event, 'Polling of STDIN failed')
        if not (event & select.POLLIN):
            return
        d = os.read(stdin_fd, io.DEFAULT_BUFFER_SIZE)
        if not d:
            raise SystemExit(0)
        input_buf += d
        while (idx := input_buf.find(b'\n')) > -1:
            line = input_buf[:idx].decode()
            input_buf = input_buf[idx+1:]
            cmd, _, payload = line.partition(':')
            if cmd == 'reload_kitty_config':
                os.environ['KITTY_PREWARM_CONFIG'] = payload
                reload_kitty_config()
            elif cmd == 'ready':
                child_id = int(payload)
                cfd = child_ready_fds.pop(child_id)
                if cfd is not None:
                    os.write(cfd, b'1')
                    os.close(cfd)
            elif cmd == 'fork':
                r, w = os.pipe()
                os.set_inheritable(w, False)
                try:
                    child_pid, child_death_fd = fork(payload, r)
                except Exception as e:
                    es = str(e).replace('\n', ' ')
                    output_buf += f'ERR:{es}\n'.encode()
                else:
                    if os.getpid() == self_pid:
                        child_id = next(child_id_counter)
                        child_id_map[child_id] = child_pid
                        child_ready_fds[child_id] = w
                        child_death_fds[child_death_fd] = child_id
                        poll.register(child_death_fd, select.POLLIN)
                        output_buf += f'CHILD:{child_id}:{child_pid}\n'.encode()
                finally:
                    if os.getpid() == self_pid:
                        os.close(r)
            elif cmd == 'echo':
                output_buf += f'{payload}\n'.encode()

    def handle_output(event: int) -> None:
        nonlocal output_buf
        check_event(event, 'Polling of STDOUT failed')
        if not (event & select.POLLOUT):
            return
        if output_buf:
            n = os.write(stdout_fd, output_buf)
            if not n:
                raise SystemExit(0)
            output_buf = output_buf[n:]
        if not output_buf:
            poll.unregister(stdout_fd)

    def handle_notify_child_death(event: int) -> None:
        nonlocal child_death_buf
        check_event(event, 'Polling of notify child death fd failed')
        if not (event & select.POLLOUT):
            return
        if child_death_buf:
            n = os.write(notify_child_death_fd, child_death_buf)
            if not n:
                raise SystemExit(0)
            child_death_buf = child_death_buf[n:]
        if not child_death_buf:
            poll.unregister(notify_child_death_fd)

    def handle_child_death(dead_child_fd: int, dead_child_id: int) -> None:
        nonlocal child_death_buf
        poll.unregister(dead_child_fd)
        del child_death_fds[dead_child_fd]
        xfd = child_ready_fds.pop(dead_child_id, None)
        if xfd is not None:
            os.close(xfd)
        dead_child_pid = child_id_map.pop(dead_child_id)
        if dead_child_pid is not None:
            child_death_buf += f'{dead_child_pid}\n'.encode()

    try:
        while True:
            if output_buf:
                poll.register(stdout_fd, select.POLLOUT)
            if child_death_buf:
                poll.register(notify_child_death_fd, select.POLLOUT)
            for (q, event) in poll.poll():
                if q == stdin_fd:
                    handle_input(event)
                elif q == stdout_fd:
                    handle_output(event)
                elif q == notify_child_death_fd:
                    handle_notify_child_death(event)
                else:
                    dead_child_id = child_death_fds.get(q)
                    if dead_child_id is not None and event & select.POLLHUP:
                        handle_child_death(q, dead_child_id)
    except (KeyboardInterrupt, EOFError, BrokenPipeError):
        if os.getpid() == self_pid:
            raise SystemExit(1)
        raise
    except Exception:
        if os.getpid() == self_pid:
            import traceback
            traceback.print_exc()
        raise
    finally:
        if os.getpid() == self_pid:
            for fmd in child_ready_fds.values():
                with suppress(OSError):
                    os.close(fmd)