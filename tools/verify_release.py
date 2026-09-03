# SPDX-License-Identifier: MIT
"""Fail-closed offline verifier for the public release directory."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
SUMS = ROOT / "SHA256SUMS.txt"
FIRMWARE_PATH = Path("firmware/34410A_front_panel_firmware.bin")
FIRMWARE_LENGTH = 4162
FIRMWARE_SHA256 = "55779328f8d9de6675ac3a145f846cfc3f86aaa346136698ef4df31edc15c4dd"
FORBIDDEN_SUFFIXES = {".elf", ".hex", ".ihex", ".srec", ".s19", ".pdf", ".zip", ".7z", ".rar", ".gz", ".xz", ".img", ".dump", ".dmp", ".log", ".gpr", ".gzf"}
FORBIDDEN_PARTS = {"__pycache__", ".pytest_cache", ".git"}
CYRILLIC = re.compile(r"[\u0400-\u04ff]")
REQUIRED = {
    "README.md", "LICENSE", "NOTICE.md",
    "RELEASE_CHECKLIST.md", "release_manifest.json",
    "docs/PROTOCOL.md", "docs/PHYSICAL_INTERFACE.md",
    "docs/ORIGINAL_FIRMWARE_UPDATE.md", "docs/ORIGINAL_MCU_INTERNALS.md",
    "docs/PROVENANCE.md", "docs/OPEN_QUESTIONS.md",
    "firmware/34410A_front_panel_firmware.bin",
    "data/commands.csv", "data/j1102_pinout.csv", "data/annunciators.csv",
    "data/keys.csv", "data/original_firmware_update.json",
    "data/original_mcu_architecture.json", "data/original_mcu_function_map.csv",
    "derived/front_panel_protocol_extract.json",
    "derived/original_mcu_trace_results.json", "reference_model/model.py",
    "reference_model/fixtures/traces.json", "tests/test_reference_model.py",
    "tests/test_publication_data.py", "examples/transactions.json",
}


def relative_files() -> list[Path]:
    files = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT)
        if any(part in FORBIDDEN_PARTS for part in rel.parts):
            continue
        if rel.as_posix() == SUMS.name:
            continue
        files.append(rel)
    return sorted(files, key=lambda item: item.as_posix())


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def expected_sums() -> str:
    return "".join(f"{digest(ROOT / rel)}  {rel.as_posix()}\n" for rel in relative_files())


def validate_firmware(errors: list[str]) -> None:
    binaries = [rel for rel in relative_files() if rel.suffix.lower() == ".bin"]
    if binaries != [FIRMWARE_PATH]:
        errors.append("the package must contain exactly the approved original-panel binary")
        return
    path = ROOT / FIRMWARE_PATH
    image = path.read_bytes()
    if len(image) != FIRMWARE_LENGTH:
        errors.append("included original-panel firmware length is incorrect")
    if hashlib.sha256(image).hexdigest() != FIRMWARE_SHA256:
        errors.append("included original-panel firmware SHA-256 is incorrect")
    if image[0x1000:0x100E].hex() != "000960001e010000000000000000":
        errors.append("included original-panel firmware metadata is incorrect")
    if image.count(b"\x12\xff\x03") != 2:
        errors.append("included original-panel firmware ROM-call inventory is incorrect")


def validate_english_only(errors: list[str]) -> None:
    for rel in relative_files():
        if rel == FIRMWARE_PATH:
            continue
        try:
            text = (ROOT / rel).read_text(encoding="utf-8")
        except UnicodeDecodeError:
            errors.append(f"unexpected non-UTF-8 public file: {rel.as_posix()}")
            continue
        if CYRILLIC.search(text):
            errors.append(f"Cyrillic text is not allowed in the public package: {rel.as_posix()}")


def validate_semantics(errors: list[str]) -> None:
    manifest = json.loads((ROOT / "release_manifest.json").read_text(encoding="utf-8"))
    if manifest.get("release") != "1.0.1":
        errors.append("manifest release must be 1.0.1")
    if manifest.get("publication_status") != "PUBLIC_RELEASE":
        errors.append("manifest must be PUBLIC_RELEASE after owner approval")
    if manifest.get("redistributed_proprietary_artifacts") is not True:
        errors.append("manifest must disclose redistribution of the included firmware")
    included = manifest.get("included_firmware", {})
    if included.get("path") != FIRMWARE_PATH.as_posix():
        errors.append("manifest firmware path is incorrect")
    if included.get("length") != FIRMWARE_LENGTH:
        errors.append("manifest firmware length is incorrect")
    if included.get("sha256") != FIRMWARE_SHA256:
        errors.append("manifest firmware SHA-256 is incorrect")
    if included.get("publication_basis") != "project_owner_explicitly_authorized_inclusion_and_confirmed_licensing":
        errors.append("manifest firmware publication basis is missing")

    scope = manifest.get("scope", {})
    for key in (
        "original_lpc932_isp_wire_protocol",
        "stock_ppc_update_flow",
        "original_mcu_startup_and_main_loop",
        "original_mcu_uart_parser",
        "original_mcu_keypad_fifo_srq",
    ):
        if not str(scope.get(key, "")).startswith("DIRECT_STATIC_CLOSED"):
            errors.append(f"original-panel scope is not statically closed: {key}")

    extract = json.loads((ROOT / "derived/front_panel_protocol_extract.json").read_text(encoding="utf-8"))
    if extract.get("firmware", {}).get("length") != FIRMWARE_LENGTH:
        errors.append("unexpected evidence firmware length")

    update = json.loads((ROOT / "data/original_firmware_update.json").read_text(encoding="utf-8"))
    image = update.get("firmware_image", {})
    if image.get("length") != FIRMWARE_LENGTH or image.get("revision") != "0x0009":
        errors.append("unexpected original-panel image identity/revision")
    if image.get("sha256") != FIRMWARE_SHA256:
        errors.append("unexpected original-panel image hash")
    embeddings = update.get("ppc_embeddings", [])
    if len(embeddings) != 2 or not all(row.get("slice_identical") is True for row in embeddings):
        errors.append("both PPC embeddings must be present and byte-identical")
    operations = {row["operation"] for row in update.get("records", [])}
    required_operations = {
        "program_data", "program_uconfig", "program_boot_vector",
        "program_status", "program_security_n", "read_uconfig",
        "read_boot_vector", "read_status", "read_security_n",
        "read_manufacturer_id", "read_device_id_1", "read_device_id_2",
        "erase_page", "erase_sector",
    }
    if operations != required_operations:
        errors.append("original ISP record inventory is incomplete")

    mcu = json.loads((ROOT / "data/original_mcu_architecture.json").read_text(encoding="utf-8"))
    if mcu.get("image", {}).get("recovered_function_count") != 71:
        errors.append("unexpected original MCU recovered function count")
    if mcu.get("startup", {}).get("xram_cleared_bytes") != 512:
        errors.append("unexpected original MCU startup XRAM clear size")
    if mcu.get("subsystems", {}).get("uart", {}).get("dispatch_entries") != 64:
        errors.append("unexpected original MCU dispatch table size")
    if mcu.get("subsystems", {}).get("sound", {}).get("tone_reload_pairs") != 85:
        errors.append("unexpected original MCU tone table size")
    if mcu.get("edge_cases", {}).get("display_count_zero_store_count") != 256:
        errors.append("original MCU zero-count edge case is missing")

    with (ROOT / "data/original_mcu_function_map.csv").open(encoding="utf-8", newline="") as stream:
        functions = list(csv.DictReader(stream))
    addresses = [row["address"] for row in functions]
    if len(functions) != 71 or len(set(addresses)) != 71:
        errors.append("original MCU function map must contain 71 unique entries")
    if addresses[:1] != ["0x0003"] or addresses[-1:] != ["0x103f"]:
        errors.append("original MCU function-map address bounds are unexpected")

    traces = json.loads((ROOT / "derived/original_mcu_trace_results.json").read_text(encoding="utf-8"))
    if {row.get("name") for row in traces} != {"startup", "command_21_count_zero", "reply_tb8"}:
        errors.append("original MCU closure-trace inventory is incomplete")

    with (ROOT / "data/commands.csv").open(encoding="utf-8", newline="") as stream:
        commands = list(csv.DictReader(stream))
    expected = {"0x01", "0x03", "0x05", "0x12", "0x13", "0x14", "0x15", "0x21", "0x31", "0x32", "0x33", "0x34", "0x36", "0x38", "0x3A"}
    if {row["opcode"] for row in commands} != expected:
        errors.append("command inventory is not the exact implemented set")

    with (ROOT / "data/j1102_pinout.csv").open(encoding="utf-8", newline="") as stream:
        pins = list(csv.DictReader(stream))
    if [int(row["pin"]) for row in pins] != list(range(1, 13)):
        errors.append("J1102 must contain pins 1..12 exactly once")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-sums", action="store_true")
    args = parser.parse_args()
    errors: list[str] = []
    present = {path.as_posix() for path in relative_files()}
    missing = sorted(REQUIRED - present)
    if missing:
        errors.append("missing required files: " + ", ".join(missing))
    forbidden_dirs = sorted({
        part for path in ROOT.rglob("*")
        for part in path.relative_to(ROOT).parts if part in FORBIDDEN_PARTS and part != ".git"
    })
    if forbidden_dirs:
        errors.append("forbidden generated directories: " + ", ".join(forbidden_dirs))
    for rel in relative_files():
        if rel.suffix.lower() in FORBIDDEN_SUFFIXES:
            errors.append(f"forbidden artifact: {rel.as_posix()}")
    validate_firmware(errors)
    validate_english_only(errors)
    try:
        validate_semantics(errors)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        errors.append(f"semantic validation failed: {exc}")
    wanted = expected_sums()
    if args.write_sums:
        SUMS.write_text(wanted, encoding="utf-8", newline="\n")
    elif not SUMS.exists():
        errors.append("SHA256SUMS.txt is missing")
    elif SUMS.read_text(encoding="utf-8") != wanted:
        errors.append("SHA256SUMS.txt does not match package contents")
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"OK: {len(relative_files())} files; English-only public release is internally consistent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())