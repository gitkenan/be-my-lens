"""Line coverage for the Lua plugins, without LuaCov.

Enabled by setting JIESHUO_LUA_COVERAGE to an output path (./run-tests.sh --coverage does).

* Executable lines come from the Lua compiler itself: each script is compiled and
  dumped with string.dump, and the line table of every function prototype is read
  from the Lua 5.3 bytecode, so comments, blank lines and `local x =` continuation
  lines are never counted.
* Hit lines come from a debug.sethook line hook installed before the plugin runs. It
  stays active for callbacks Jieshuo calls later (onScreenCaptureDone, ...).
"""

from __future__ import annotations

import json
import os
import struct
from pathlib import Path

from lupa import lua53

_OUTPUT = os.environ.get("JIESHUO_LUA_COVERAGE")
_executable: dict[str, set[int]] = {}
_hits: dict[str, set[int]] = {}


def enabled() -> bool:
    return bool(_OUTPUT)


def chunk_name(path: Path, repo_root: Path) -> str:
    try:
        return "@" + path.resolve().relative_to(repo_root).as_posix()
    except ValueError:
        return "@" + path.name


def install_hook(runtime) -> None:
    """Record (chunk, line) for every line executed in this runtime from now on."""
    hits = runtime.eval(
        """
        function()
          local hits, getinfo = {}, debug.getinfo
          debug.sethook(function(_, line)
            local source = getinfo(2, "S").source
            local lines = hits[source]
            if lines == nil then lines = {}; hits[source] = lines end
            lines[line] = true
          end, "l")
          return hits
        end
        """
    )()
    _live_tables.append(hits)


_live_tables: list = []


def collect() -> None:
    """Fold hit tables from finished runtimes into the totals."""
    while _live_tables:
        table = _live_tables.pop()
        for source, lines in table.items():
            _hits.setdefault(source, set()).update(int(line) for line in lines.keys())


def register_script(path: Path, name: str) -> None:
    if name not in _executable:
        _executable[name] = executable_lines(path.read_bytes(), name)


def write() -> None:
    collect()
    files = {
        name.removeprefix("@"): {
            "executable": sorted(lines),
            "hit": sorted(_hits.get(name, set()) & lines),
        }
        for name, lines in sorted(_executable.items())
    }
    Path(_OUTPUT).parent.mkdir(parents=True, exist_ok=True)
    Path(_OUTPUT).write_text(json.dumps({"files": files}, indent=2))


# Lua 5.3 bytecode ------------------------------------------------------------------


def executable_lines(source: bytes, name: str) -> set[int]:
    runtime = lua53.LuaRuntime(encoding=None)
    dump = runtime.eval("function(src, name) return string.dump(assert(load(src, name))) end")(source, name.encode())
    return _BytecodeReader(dump).lines()


class _BytecodeReader:
    """Reads the line tables out of a Lua 5.3 string.dump (ldump.c)."""

    def __init__(self, data: bytes):
        self.data, self.pos = data, 0

    def lines(self) -> set[int]:
        assert self.take(4) == b"\x1bLua" and self.byte() == 0x53, "not Lua 5.3 bytecode"
        self.take(1 + 6)  # format, LUAC_DATA
        self.int_size, self.size_t_size, instruction, integer, number = self.take(5)
        assert (instruction, integer, number) == (4, 8, 8), "unexpected Lua build"
        self.take(integer + number)  # LUAC_INT, LUAC_NUM
        self.byte()  # main function upvalue count
        found: set[int] = set()
        self.function(found)
        return found

    def take(self, count: int) -> bytes:
        chunk = self.data[self.pos : self.pos + count]
        self.pos += count
        return chunk

    def byte(self) -> int:
        return self.take(1)[0]

    def read_int(self) -> int:
        return struct.unpack("<i", self.take(self.int_size))[0]

    def string(self) -> None:
        size = self.byte()
        if size == 0xFF:
            size = struct.unpack("<Q", self.take(self.size_t_size))[0]
        if size:
            self.take(size - 1)

    def function(self, found: set[int]) -> None:
        self.string()  # source
        self.take(2 * self.int_size)  # linedefined, lastlinedefined
        self.take(3)  # numparams, is_vararg, maxstacksize
        self.take(4 * self.read_int())  # code
        for _ in range(self.read_int()):  # constants
            kind = self.byte()
            if kind == 1:
                self.byte()
            elif kind in (3, 19):
                self.take(8)
            elif kind in (4, 20):
                self.string()
        self.take(2 * self.read_int())  # upvalues
        for _ in range(self.read_int()):  # nested functions
            self.function(found)
        count = self.read_int()  # line table: one source line per instruction
        found.update(struct.unpack(f"<{count}i", self.take(4 * count)))
        for _ in range(self.read_int()):  # local variables
            self.string()
            self.take(2 * self.int_size)  # startpc, endpc
        for _ in range(self.read_int()):  # upvalue names
            self.string()
