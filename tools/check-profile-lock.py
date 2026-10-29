#!/usr/bin/env python3
"""Read-only comparison of package.json and pnpm 9 root direct specifiers.

This is deliberately not a general YAML reader or a pnpm lockfile validator.
Only conventional block mappings in ``importers`` are supported (plus the
unambiguous empty mapping ``{}``). Other lockfile sections are not interpreted.
Unsupported or ambiguous importer syntax returns unknown, never consistent.
No specifier values, URLs, filesystem paths, or exception messages are emitted.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re
import sys


SECTIONS = ("dependencies", "devDependencies", "optionalDependencies")
SCOPE = "direct_specifiers_only"
PACKAGE_NAME = re.compile(r"(?:@[A-Za-z0-9_.~-]+/)?[A-Za-z0-9_.~-]+\Z")


class Unknown(Exception):
    """A safe, fixed reason code; never retain source text in diagnostics."""


@dataclass(frozen=True)
class Scalar:
    value: str
    kind: str = "string"


@dataclass(frozen=True)
class Line:
    indent: int
    text: str


_NUMBER = re.compile(
    r"[-+]?(?:[0-9][0-9_]*(?:\.[0-9_]*)?(?:[eE][-+]?[0-9_]+)?"
    r"|\.[0-9_]+(?:[eE][-+]?[0-9_]+)?"
    r"|0[xX][0-9a-fA-F_]+|0[oO][0-7_]+|0[bB][01_]+)\Z"
)
_ESCAPES = {
    "0": "\0", "a": "\a", "b": "\b", "t": "\t", "n": "\n",
    "v": "\v", "f": "\f", "r": "\r", "e": "\x1b", " ": " ",
    '"': '"', "/": "/", "\\": "\\", "N": "\x85", "_": "\xa0",
    "L": "\u2028", "P": "\u2029",
}


def _quoted_scalar(text: str) -> Scalar:
    quote = text[0]
    chars: list[str] = []
    pos = 1
    while pos < len(text):
        char = text[pos]
        if char == quote:
            if quote == "'" and pos + 1 < len(text) and text[pos + 1] == "'":
                chars.append("'")
                pos += 2
                continue
            tail = text[pos + 1:]
            if tail and (not tail[0].isspace() or not tail.lstrip().startswith("#")):
                if tail.strip():
                    raise Unknown("unsupported_yaml_scalar")
            return Scalar("".join(chars))
        if char == "\\" and quote == '"':
            pos += 1
            if pos >= len(text):
                raise Unknown("unsupported_yaml_scalar")
            escape = text[pos]
            if escape in _ESCAPES:
                chars.append(_ESCAPES[escape])
            elif escape in ("x", "u", "U"):
                width = {"x": 2, "u": 4, "U": 8}[escape]
                digits = text[pos + 1:pos + 1 + width]
                if len(digits) != width or not re.fullmatch(r"[0-9a-fA-F]+", digits):
                    raise Unknown("unsupported_yaml_scalar")
                codepoint = int(digits, 16)
                if codepoint > 0x10FFFF or 0xD800 <= codepoint <= 0xDFFF:
                    raise Unknown("unsupported_yaml_scalar")
                chars.append(chr(codepoint))
                pos += width
            else:
                raise Unknown("unsupported_yaml_scalar")
        else:
            if ord(char) < 32 and char != "\t":
                raise Unknown("unsupported_yaml_scalar")
            chars.append(char)
        pos += 1
    raise Unknown("unsupported_yaml_scalar")


def _scalar(raw: str):
    text = raw.strip()
    if text.startswith(("'", '"')):
        return _quoted_scalar(text)
    comment = re.search(r"(?:^|\s)#", text)
    if comment:
        text = text[:comment.start()].rstrip()
    if not text:
        return Scalar("", "null")
    if re.fullmatch(r"\{\s*\}", text):
        return {}
    if text.startswith(("{", "[")):
        raise Unknown("unsupported_yaml_flow")
    if re.search(r"(?:^|\s)[&*!]", text):
        raise Unknown("unsupported_yaml_reference_or_tag")
    if text.startswith(("|", ">", "@", "`", ",", "]", "}")):
        raise Unknown("unsupported_yaml_scalar")
    if re.match(r"[-?:](?:\s|$)", text) or re.search(r":(?:\s|$)", text):
        raise Unknown("unsupported_yaml_scalar")
    if text.lower() in ("null", "~"):
        return Scalar(text, "null")
    # Non-string scalars must not make a package string appear synchronized.
    if text.lower() in ("true", "false", "yes", "no", "on", "off", ".inf", "+.inf", "-.inf", ".nan"):
        return Scalar(text, "nonstring")
    if _NUMBER.fullmatch(text):
        return Scalar(text, "number")
    return Scalar(text)


def _entry(text: str):
    quote = None
    pos = 0
    while pos < len(text):
        char = text[pos]
        if quote == "'" and char == "'" and pos + 1 < len(text) and text[pos + 1] == "'":
            pos += 2
            continue
        if quote == '"' and char == "\\":
            pos += 2
            continue
        if char in ("'", '"'):
            if quote is None:
                quote = char
            elif char == quote:
                quote = None
        elif char == "#" and quote is None and (pos == 0 or text[pos - 1].isspace()):
            # A colon occurring inside a comment is not a mapping delimiter.
            raise Unknown("unsupported_yaml_mapping")
        elif char == ":" and quote is None and (pos + 1 == len(text) or text[pos + 1].isspace()):
            key = _scalar(text[:pos])
            if not isinstance(key, Scalar) or key.kind != "string" or not key.value:
                raise Unknown("unsupported_yaml_key")
            if key.value == "<<":
                raise Unknown("unsupported_yaml_merge")
            return key.value, text[pos + 1:]
        pos += 1
    raise Unknown("unsupported_yaml_mapping")


def _lines(text: str) -> list[Line]:
    result: list[Line] = []
    document_started = False
    document_ended = False
    for raw in text.splitlines():
        prefix = raw[:len(raw) - len(raw.lstrip(" \t"))]
        if "\t" in prefix:
            raise Unknown("unsupported_yaml_tab_indentation")
        content = raw.lstrip(" ")
        if not content or content.startswith("#"):
            continue
        indent = len(raw) - len(content)
        if indent == 0 and re.fullmatch(r"---(?:\s+#.*)?", content):
            if document_started or result or document_ended:
                raise Unknown("unsupported_yaml_multiple_documents")
            document_started = True
            continue
        if indent == 0 and re.fullmatch(r"\.\.\.(?:\s+#.*)?", content):
            if document_ended:
                raise Unknown("unsupported_yaml_multiple_documents")
            document_ended = True
            continue
        if document_ended:
            raise Unknown("unsupported_yaml_multiple_documents")
        result.append(Line(indent, content))
    return result


def _top_level(text: str):
    lines = _lines(text)
    entries = {}
    current = None
    for line in lines:
        if line.indent == 0:
            key, value = _entry(line.text)
            if key in entries:
                raise Unknown("duplicate_yaml_key")
            entries[key] = (value, [])
            current = key
        else:
            if current is None:
                raise Unknown("unsupported_yaml_top_level")
            entries[current][1].append(line)
    return entries


def _block(lines: list[Line], start: int, indent: int):
    mapping = {}
    pos = start
    while pos < len(lines) and lines[pos].indent >= indent:
        line = lines[pos]
        if line.indent != indent:
            raise Unknown("unsupported_yaml_indentation")
        key, raw_value = _entry(line.text)
        if key in mapping:
            raise Unknown("duplicate_yaml_key")
        value = _scalar(raw_value)
        pos += 1
        if pos < len(lines) and lines[pos].indent > indent:
            if not isinstance(value, Scalar) or value.kind != "null" or value.value:
                raise Unknown("unsupported_yaml_indentation")
            value, pos = _block(lines, pos, lines[pos].indent)
        mapping[key] = value
    return mapping, pos


def _version(entries) -> None:
    if "lockfileVersion" not in entries:
        raise Unknown("lockfile_version_missing")
    raw, children = entries["lockfileVersion"]
    value = _scalar(raw)
    if children or not isinstance(value, Scalar) or value.kind not in ("string", "number"):
        raise Unknown("unsupported_lockfile_version")
    if not re.fullmatch(r"9(?:\.\d+)?", value.value):
        raise Unknown("unsupported_lockfile_version")


def _root_importer(entries):
    if "importers" not in entries:
        raise Unknown("importers_missing")
    raw, children = entries["importers"]
    value = _scalar(raw)
    if children:
        if not isinstance(value, Scalar) or value.kind != "null" or value.value:
            raise Unknown("unsupported_importers_mapping")
        value, consumed = _block(children, 0, children[0].indent)
        if consumed != len(children):
            raise Unknown("unsupported_yaml_indentation")
    if not isinstance(value, dict):
        raise Unknown("unsupported_importers_mapping")
    if "." not in value:
        raise Unknown("root_importer_missing")
    root = value["."]
    if not isinstance(root, dict):
        raise Unknown("root_importer_not_mapping")
    return root


def _json_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise Unknown("manifest_duplicate_key")
        value[key] = item
    return value


def _invalid_json_constant(_value):
    raise Unknown("manifest_invalid_json")


def _read(path: Path, label: str) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        raise Unknown(label + "_missing") from None
    except (OSError, UnicodeError, ValueError):
        raise Unknown(label + "_unreadable") from None


def _manifest(text: str):
    try:
        manifest = json.loads(text, object_pairs_hook=_json_object, parse_constant=_invalid_json_constant)
    except (ValueError, RecursionError):
        raise Unknown("manifest_invalid_json") from None
    if not isinstance(manifest, dict):
        raise Unknown("manifest_not_object")
    dependencies = {}
    for section in SECTIONS:
        records = manifest.get(section, {})
        if not isinstance(records, dict) or any(not isinstance(value, str) for value in records.values()):
            raise Unknown("manifest_dependencies_not_string_mapping")
        if any(not PACKAGE_NAME.fullmatch(name) for name in records):
            raise Unknown("unsupported_dependency_name")
        dependencies[section] = records
    return dependencies


def _lock_dependencies(root):
    dependencies = {}
    for section in SECTIONS:
        records = root.get(section, {})
        if not isinstance(records, dict):
            raise Unknown("lock_dependencies_not_mapping")
        dependencies[section] = {}
        for name, record in records.items():
            if not PACKAGE_NAME.fullmatch(name):
                raise Unknown("unsupported_dependency_name")
            if not isinstance(record, dict):
                raise Unknown("lock_specifier_missing_or_not_string")
            specifier = record.get("specifier")
            if not isinstance(specifier, Scalar) or specifier.kind != "string":
                raise Unknown("lock_specifier_missing_or_not_string")
            dependencies[section][name] = specifier.value
    return dependencies


def _result():
    return {"schema_version": 1, "status": "unknown", "scope": SCOPE,
            "pnpm_lockfile_major": None, "differences": [], "reason_codes": []}


def check_profile(profile_root) -> dict:
    """Read only package.json and pnpm-lock.yaml; return a redacted assessment."""
    result = _result()
    try:
        profile = Path(profile_root)
        manifest = _manifest(_read(profile / "package.json", "manifest"))
        entries = _top_level(_read(profile / "pnpm-lock.yaml", "lockfile"))
        _version(entries)
        result["pnpm_lockfile_major"] = 9
        locked = _lock_dependencies(_root_importer(entries))
        differences = []
        for section in SECTIONS:
            for name in sorted(manifest[section].keys() | locked[section].keys()):
                if name not in locked[section]:
                    kind = "missing_in_lock"
                elif name not in manifest[section]:
                    kind = "extra_in_lock"
                elif manifest[section][name] != locked[section][name]:
                    kind = "specifier_mismatch"
                else:
                    continue
                differences.append({"section": section, "dependency": name, "kind": kind})
        result["differences"] = differences
        result["status"] = "mismatch" if differences else "consistent"
    except Unknown as error:
        result["reason_codes"] = [str(error)]
    except (OSError, ValueError, TypeError, RecursionError):
        result["reason_codes"] = ["input_unreadable_or_unsupported"]
    return result


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise Unknown("invalid_arguments")


def main(argv=None) -> int:
    parser = _Parser(add_help=False)
    parser.add_argument("--profile-root", required=True)
    try:
        args = parser.parse_args(argv)
        result = check_profile(args.profile_root)
    except Unknown as error:
        result = _result()
        result["reason_codes"] = [str(error)]
    except Exception:
        # CLI failures remain machine readable without disclosing local inputs.
        result = _result()
        result["reason_codes"] = ["internal_error"]
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
