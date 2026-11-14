"""Helpers to check API JSON against the frontend's REAL types.ts (read-only): key sets and a tsc compile."""
import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TYPES_TS = ROOT / "frontend" / "src" / "api" / "types.ts"
TSC = ROOT / "frontend" / "node_modules" / ".bin" / ("tsc.cmd" if shutil.which("cmd") else "tsc")


def ts_keys(interface: str):
    """(required, optional) top-level keys of `export interface <interface> { ... }` in types.ts."""
    src = TYPES_TS.read_text(encoding="utf-8")
    rest = src.split(f"export interface {interface} {{")[1]
    depth, end = 1, 0
    for i, ch in enumerate(rest):          # matching closing brace: also right for one-line interfaces like TwistSide
        depth += (ch == "{") - (ch == "}")
        if depth == 0:
            end = i
            break
    block = rest[:end]
    req, opt = set(), set()
    for ln in block.splitlines():
        ln = ln.split("//")[0]
        while re.search(r"\{[^{}]*\}", ln):          # drop nested object types: only top-level keys count
            ln = re.sub(r"\{[^{}]*\}", "T", ln)
        for part in ln.split(";"):
            if ":" in part:
                k = part.split(":")[0].strip()
                if k:
                    (opt if k.endswith("?") else req).add(k.rstrip("?"))
    return req, opt


def keys_match(obj: dict, interface: str):
    req, opt = ts_keys(interface)
    return req <= set(obj) <= req | opt


def tsc_ok(tmp_path, type_name: str, obj, name="check"):
    """Compile `obj` as a `type_name` literal against the real types.ts. Returns (ok, compiler output)."""
    ts = tmp_path / f"{name}.ts"
    ts.write_text(f'import type {{ {type_name} }} from "{TYPES_TS.as_posix()[:-3]}";\n'
                  f"export const x: {type_name} = {json.dumps(obj, ensure_ascii=False)};\n", encoding="utf-8")
    out = subprocess.run([str(TSC), "--noEmit", "--strict", "--skipLibCheck", "--target", "es2020",
                          "--module", "esnext", "--moduleResolution", "bundler", str(ts)], capture_output=True, text=True)
    return out.returncode == 0, out.stdout + out.stderr
