"""Combined coverage report across the backend, the Jieshuo plugins and the Android app.

Used by ./run-tests.sh --coverage. Reads whichever reports exist:

* build/coverage/backend.xml   coverage.py (Cobertura XML) for server/
* build/coverage/lua.json      Lua line coverage from tests/jieshuo (lua_coverage.py)
* tests/android-jvm/build/reports/jacoco/coverageReport/coverageReport.xml   JaCoCo

Each tool defines a "line" slightly differently (statements, Lua line-table entries,
lines with bytecode). Android files that the JVM harness cannot compile (Compose UI,
Activities) have no measured lines. They are reported as uncovered, sized by counting
their code lines scaled to JaCoCo's line definition using the measured files as a
reference; totals that include them are marked as estimates.
"""

from __future__ import annotations

import argparse
import json
import re
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BACKEND_XML = REPO / "build/coverage/backend.xml"
LUA_JSON = REPO / "build/coverage/lua.json"
JACOCO_XML = REPO / "tests/android-jvm/build/reports/jacoco/coverageReport/coverageReport.xml"
ANDROID_SOURCES = REPO / "app/src/main/java"


@dataclass
class Row:
    area: str
    name: str
    covered: int
    total: int
    note: str = ""
    estimated: bool = False

    @property
    def percent(self) -> str:
        return f"{100 * self.covered / self.total:5.1f}%" if self.total else "   n/a"


def backend_rows() -> list[Row]:
    root = ElementTree.parse(BACKEND_XML).getroot()
    rows = []
    for cls in root.iter("class"):
        lines = cls.findall("lines/line")
        covered = sum(1 for line in lines if int(line.get("hits", "0")) > 0)
        branch = f"branches {float(cls.get('branch-rate', 0)) * 100:.0f}%"
        rows.append(Row("Backend", "server/" + cls.get("filename"), covered, len(lines), branch))
    return rows


def lua_rows() -> list[Row]:
    files = json.loads(LUA_JSON.read_text())["files"]
    rows = []
    for name, data in files.items():
        area = "Jieshuo plugins" if name.startswith("dist/") else "Jieshuo prototypes"
        rows.append(Row(area, name, len(data["hit"]), len(data["executable"])))
    return rows


def android_rows() -> list[Row]:
    root = ElementTree.parse(JACOCO_XML).getroot()
    rows, measured = [], set()
    for package in root.findall("package"):
        for source in package.findall("sourcefile"):
            counters = {c.get("type"): c for c in source.findall("counter")}
            line = counters.get("LINE")
            if line is None:
                continue
            covered, missed = int(line.get("covered")), int(line.get("missed"))
            branch = counters.get("BRANCH")
            note = ""
            if branch is not None:
                b_cov, b_miss = int(branch.get("covered")), int(branch.get("missed"))
                note = f"branches {100 * b_cov / (b_cov + b_miss):.0f}%"
            path = f"{package.get('name')}/{source.get('name')}"
            measured.add(path)
            rows.append(Row("Android", "app/src/main/java/" + path, covered, covered + missed, note))
    # Size unmeasured files in JaCoCo-equivalent lines: count their code lines, then scale
    # by how JaCoCo's counts compare with that same count on the measured files.
    measured_code_lines = sum(code_lines(ANDROID_SOURCES / path) for path in measured)
    scale = sum(row.total for row in rows) / measured_code_lines if measured_code_lines else 1.0
    for source in sorted(ANDROID_SOURCES.rglob("*.kt")):
        path = source.relative_to(ANDROID_SOURCES).as_posix()
        if path not in measured:
            size = max(1, round(code_lines(source) * scale))
            rows.append(Row("Android", "app/src/main/java/" + path, 0, size, "not run by any suite (size estimated)", True))
    return rows


def code_lines(source: Path) -> int:
    """Lines of code: not blank, not comments, not imports, not lone brackets."""
    text = re.sub(r"/\*.*?\*/", "", source.read_text(encoding="utf-8"), flags=re.S)
    count = 0
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(("//", "import ", "package ")) or re.fullmatch(r"[{}()\[\],]+", line):
            continue
        count += 1
    return count


def render(rows: list[Row], sections: list[str]) -> str:
    out = []
    width = max(len(row.name) for row in rows) if rows else 40
    for area in sections:
        area_rows = [row for row in rows if row.area == area]
        if not area_rows:
            continue
        covered = sum(row.covered for row in area_rows)
        total = sum(row.total for row in area_rows)
        estimated = any(row.estimated for row in area_rows)
        out.append(f"\n{area}")
        for row in sorted(area_rows, key=lambda r: (r.estimated, r.name)):
            out.append(f"  {row.name:<{width}}  {row.covered:5}/{row.total:<5} {row.percent}  {row.note}")
        label = "total (estimate: includes unmeasured files)" if estimated else "total"
        out.append(f"  {label:<{width}}  {covered:5}/{total:<5} {Row('', '', covered, total).percent}")
    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--suites", default="backend,jieshuo,android", help="suites that ran in this invocation")
    parser.add_argument("--markdown", type=Path, help="also write the report to this file")
    args = parser.parse_args()
    suites = set(args.suites.split(","))

    rows: list[Row] = []
    missing = []
    for suite, path, reader in (
        ("backend", BACKEND_XML, backend_rows),
        ("jieshuo", LUA_JSON, lua_rows),
        ("android", JACOCO_XML, android_rows),
    ):
        if suite not in suites:
            continue
        if path.exists():
            rows += reader()
        else:
            missing.append(f"{suite} (no report at {path.relative_to(REPO)})")

    sections = ["Backend", "Jieshuo plugins", "Jieshuo prototypes", "Android"]
    report = "Coverage (lines covered / lines)" + render(rows, sections)

    shipped = [row for row in rows if row.area != "Jieshuo prototypes"]
    if {"backend", "jieshuo", "android"} <= suites and not missing:
        covered = sum(row.covered for row in shipped)
        total = sum(row.total for row in shipped)
        measured = [row for row in shipped if not row.estimated]
        m_cov, m_tot = sum(r.covered for r in measured), sum(r.total for r in measured)
        report += (
            "\n\nWhole codebase (backend + shipped plugins + Android app, prototypes excluded)"
            f"\n  code the suites can run:            {m_cov:5}/{m_tot:<5} {Row('', '', m_cov, m_tot).percent}"
            f"\n  including unmeasured Android files: {covered:5}/{total:<5} {Row('', '', covered, total).percent}  (estimate)"
        )
    if missing:
        report += "\n\nMissing reports: " + ", ".join(missing)
    report += (
        "\n\nDetailed reports: build/coverage/backend-html/index.html, build/coverage/lua.json,"
        "\n  tests/android-jvm/build/reports/jacoco/coverageReport/html/index.html"
    )
    print(report)
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text("```text\n" + report + "\n```\n")


if __name__ == "__main__":
    main()
