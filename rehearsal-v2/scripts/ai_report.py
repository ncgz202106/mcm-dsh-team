#!/usr/bin/env python3
"""Build a traceable AI-use report from filtered, visible DSH audit snapshots.

No hidden reasoning, system/developer prompts, tool-return dumps or attachments are
copied into the report. User-role queries may be delegated agent tasks rather than
messages authored by a person. A draft is not a COMAP compliance certificate.

Final-use record (one per visible query, including reviewed non-adopted queries):
  record_id, session_id, query_event_seq, assistant_event_seqs, purpose,
  adoption_status=adopted|not_adopted, synthetic=false,
  human_check={status:verified, source:human, checked_by, checked_at,
               evidence_ref:{path,sha256}},
  citations_verified=true and citation_evidence=[{path,sha256}] if adopted.
The evidence_ref JSON must name source=human, synthetic=false, record_id,
checked_by, checked_at, query_sha256, response_sha256, adoption_status and
purpose (exactly matching the use record) and purpose_confirmed=true. Adopted
uses additionally require citations_verified=true. Human checks are performed in
batches at the existing H2/H3 gates; this tool introduces no per-query live gate.
For a use without source-dependent claims, the human citation evidence can explain
why citations are not applicable. Adopted attachment references also require
attachment_checks=[{attachment_id,path,sha256,checked_by}] for the original files.

This checks consistency of supplied human records, not the identity of their author
or the semantic truth of a citation. Never manufacture such records to pass --final.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys


def sha256_bytes(value):
    return hashlib.sha256(value).hexdigest()


def text_hash(value):
    return sha256_bytes(value.encode("utf-8"))


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def relative_file(root, relative):
    if not isinstance(relative, str) or not relative:
        raise ValueError("Evidence paths must be non-empty project-relative strings")
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("Evidence path must be relative without '..'")
    resolved = (Path(root).resolve() / path).resolve()
    if not resolved.is_relative_to(Path(root).resolve()):
        raise ValueError("Evidence path escapes its declared root")
    return resolved


def checked_reference(root, ref):
    if not isinstance(ref, dict):
        raise ValueError("File evidence must include path and sha256")
    path = relative_file(root, ref.get("path"))
    if not path.is_file():
        raise ValueError(f"Missing evidence file: {ref.get('path')}")
    digest = sha256_bytes(path.read_bytes())
    if not isinstance(ref.get("sha256"), str) or digest != ref["sha256"]:
        raise ValueError(f"Evidence SHA256 mismatch: {ref.get('path')}")
    return path


def json_lines(path):
    rows = []
    for number, line in enumerate(Path(path).read_text(encoding="utf-8-sig").splitlines(), 1):
        if line.strip():
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {Path(path).name}:{number}") from exc
            if not isinstance(row, dict):
                raise ValueError("JSONL records must be objects")
            rows.append(row)
    return rows


def attachment_ids(value):
    found = set()
    if isinstance(value, dict):
        if isinstance(value.get("attachmentId"), str):
            found.add(value["attachmentId"])
        for item in value.values():
            found.update(attachment_ids(item))
    elif isinstance(value, list):
        for item in value:
            found.update(attachment_ids(item))
    return found


def visible_message(event):
    data = event.get("data", {})
    if not isinstance(data, dict):
        raise ValueError("Message event data must be an object")
    message = data.get("message", data)
    if not isinstance(message, dict):
        raise ValueError("Message payload must be an object")
    return message


def message_text(message):
    content = message.get("content", [])
    if isinstance(content, str):
        text = content
    elif not isinstance(content, list):
        raise ValueError("Unknown visible message content shape")
    else:
        # Only literal visible text blocks are eligible. Reasoning/thinking blocks,
        # tool calls, images and arbitrary object strings never become report text.
        text = "\n".join(block["text"] for block in content
                         if isinstance(block, dict) and block.get("type") == "text"
                         and isinstance(block.get("text"), str))
    if any(ord(char) < 32 and char not in "\r\n\t" for char in text):
        raise ValueError("Visible text contains unsupported control characters")
    return text


def model_pair(value):
    if isinstance(value, dict) and all(isinstance(value.get(k), str) and value[k].strip()
                                       for k in ("provider", "model")):
        return {"provider": value["provider"], "model": value["model"]}
    return None


def load_archives(archives):
    sessions, provenance, warnings = {}, [], []
    for folder in archives:
        folder = Path(folder).resolve()
        manifest_path = folder / "manifest.json"
        manifest = read_json(manifest_path)
        if manifest.get("schema_version") != 1 or not isinstance(manifest.get("sessions"), list):
            raise ValueError("Unsupported audit manifest schema")
        indexes = json_lines(folder / "ai-use-index.jsonl")
        index_by_id = {r.get("session_id"): r for r in indexes}
        if len(index_by_id) != len(indexes) or None in index_by_id:
            raise ValueError("Duplicate or missing AI-index session ID")
        listed = manifest["sessions"]
        ids = [row.get("session_id") for row in listed]
        if len(set(ids)) != len(ids) or any(not isinstance(i, str) or not i for i in ids):
            raise ValueError("Duplicate or missing manifest session ID")
        if set(index_by_id) != set(ids):
            raise ValueError("AI-index and manifest session coverage disagree")
        if manifest.get("archived_sessions") != len(ids):
            raise ValueError("Manifest archived-session count is inconsistent")
        if manifest.get("discovered_sessions", -1) < len(ids):
            raise ValueError("Manifest discovered-session count is inconsistent")
        if manifest.get("transcripts_complete") is not True or manifest.get("discovered_sessions") != len(ids):
            warnings.append(f"Partial transcript tree in {folder.name}")
        if manifest.get("warnings"):
            warnings.append(f"Archive {folder.name} has recorded warnings")
        attachments = read_json(folder / "attachments.json")
        if attachments.get("archived_bytes") is not False or manifest.get("attachment_bytes_included") is not False:
            raise ValueError("Unsupported attachment coverage claim; expected reference-only archive")
        references = attachments.get("references")
        if not isinstance(references, list):
            raise ValueError("Missing attachment reference manifest")
        attachment_map = {r.get("attachmentId"): r for r in references if isinstance(r, dict)}
        if len(attachment_map) != len(references) or None in attachment_map:
            raise ValueError("Invalid/duplicate attachment reference ID")
        if manifest.get("attachment_count") != len(attachment_map):
            raise ValueError("Attachment reference count differs from manifest")
        if any(r.get("archived_bytes") is not False for r in references):
            raise ValueError("Audit references must not claim archived attachment bytes")
        archive_ref = {
            "directory": str(folder), "manifest_sha256": sha256_bytes(manifest_path.read_bytes()),
            "index_sha256": sha256_bytes((folder / "ai-use-index.jsonl").read_bytes()),
            "captured_at": manifest.get("captured_at"),
            "transcripts_complete": manifest.get("transcripts_complete") is True,
            "attachment_count": len(references), "attachment_bytes_included": False,
        }
        provenance.append(archive_ref)
        for row in listed:
            path = checked_reference(folder, row)
            lines = json_lines(path)
            if not lines or lines[0].get("type") != "mcm-visible-session" or lines[0].get("schema_version") != 1:
                raise ValueError("Missing filtered visible-session header")
            sid = row["session_id"]
            header = lines[0].get("header", {})
            if header.get("id") != sid:
                raise ValueError("Session header does not match manifest identity")
            events = lines[1:]
            seqs = [e.get("seq") for e in events]
            if any(type(seq) is not int or seq < 0 for seq in seqs) or seqs != sorted(set(seqs)):
                raise ValueError("Session events need unique increasing integer sequences")
            if row.get("visible_event_count") != len(events):
                raise ValueError("Visible-event count differs from archived bytes")
            cutoff = row.get("exported_through_seq")
            if seqs and (type(cutoff) is not int or cutoff < max(seqs)):
                raise ValueError("Session cutoff is earlier than visible events")
            output_seqs = [e["seq"] for e in events if e.get("type") == "assistant/message"]
            if index_by_id[sid].get("visible_output_event_seqs") != output_seqs:
                raise ValueError("AI-index output references do not match the transcript")
            found_attachments = attachment_ids(events)
            if found_attachments - attachment_map.keys():
                raise ValueError("Transcript attachment is absent from attachment manifest")
            entry = sessions.setdefault(sid, {"session_id": sid, "parent_session_id": header.get("parentSession"),
                "role_preset": row.get("role_preset"), "events": {}, "archive_refs": [], "index_models": []})
            if entry["parent_session_id"] != header.get("parentSession"):
                raise ValueError("Conflicting session lineage across snapshots")
            entry["archive_refs"].append({**archive_ref, "session_path": row["path"],
                                          "session_sha256": row["sha256"], "cutoff": cutoff})
            entry["role_preset"] = row.get("role_preset") or entry["role_preset"]
            for pair in index_by_id[sid].get("actual_models", []):
                normalized = model_pair(pair)
                if normalized and normalized not in entry["index_models"]:
                    entry["index_models"].append(normalized)
            for event in events:
                old = entry["events"].get(event["seq"])
                if old is not None and old != event:
                    raise ValueError("Conflicting bytes for an immutable session event across snapshots")
                entry["events"][event["seq"]] = event
    return sessions, provenance, warnings


def extract_exchanges(sessions):
    exchanges, warnings = [], []
    for sid, session in sorted(sessions.items()):
        current, route, recorded_models = None, None, []
        for event in sorted(session["events"].values(), key=lambda e: e["seq"]):
            event_type = event.get("type")
            if event_type == "request/context":
                route = model_pair(event.get("data"))
                if route and route not in recorded_models:
                    recorded_models.append(route)
            elif event_type == "user/message":
                if current is not None:
                    exchanges.append(current)
                message = visible_message(event)
                current = {"session_id": sid, "role_preset": session["role_preset"],
                    "query_event_seq": event["seq"], "query": message_text(message),
                    "assistant_event_seqs": [], "responses": [], "models": [],
                    "attachment_ids": sorted(attachment_ids(message)),
                    "archive_refs": session["archive_refs"]}
            elif event_type == "assistant/message":
                message = visible_message(event)
                actual = model_pair(message.get("source")) or route
                if actual and actual not in recorded_models:
                    recorded_models.append(actual)
                if current is None:
                    if message_text(message):
                        warnings.append(f"Unpaired assistant output in {sid}:{event['seq']}")
                    continue
                current["assistant_event_seqs"].append(event["seq"])
                current["responses"].append(message_text(message))
                current["attachment_ids"] = sorted(set(current["attachment_ids"]) | attachment_ids(message))
                if actual and actual not in current["models"]:
                    current["models"].append(actual)
                if actual is None:
                    warnings.append(f"Missing actual model for {sid}:{event['seq']}")
        if current is not None:
            exchanges.append(current)
        # The index must agree with actual visible route/source records. It does
        # not grant permission to invent a model missing from the transcript.
        if recorded_models and set((m["provider"], m["model"]) for m in recorded_models) != set(
                (m["provider"], m["model"]) for m in session["index_models"]):
            raise ValueError(f"Actual-model index disagrees with visible source/context in session {sid}")
        if not recorded_models:
            warnings.append(f"No actual model recorded for session {sid}")
    for exchange in exchanges:
        exchange["response"] = "\n\n".join(exchange["responses"])
        exchange["query_sha256"] = text_hash(exchange["query"])
        exchange["response_sha256"] = text_hash(exchange["response"])
    return exchanges, warnings


def timestamp(value):
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.tzinfo is not None
    except ValueError:
        return False


def check_use(project, exchange, record):
    """Validate a supplied human record without asserting real-world identity."""
    if not record or record.get("_template_only") or record.get("synthetic") is not False:
        raise ValueError("Each final interaction needs a real, instantiated human-use record")
    if record.get("assistant_event_seqs") != exchange["assistant_event_seqs"]:
        raise ValueError("Human-use record must cover every corresponding assistant event")
    if not isinstance(record.get("record_id"), str) or not record["record_id"].strip():
        raise ValueError("Human-use record needs record_id")
    if not isinstance(record.get("purpose"), str) or not record["purpose"].strip():
        raise ValueError("Human-use record needs the actual purpose")
    adopted = record.get("adoption_status")
    if adopted not in {"adopted", "not_adopted"}:
        raise ValueError("Human-use adoption_status must be adopted or not_adopted")
    check = record.get("human_check", {})
    if check.get("status") != "verified" or check.get("source") != "human" or not check.get("checked_by") or not timestamp(check.get("checked_at")):
        raise ValueError("Final report requires a supplied, dated human verification record")
    evidence_path = checked_reference(project, check.get("evidence_ref"))
    proof = read_json(evidence_path)
    expected = {"source": "human", "synthetic": False, "record_id": record["record_id"],
        "checked_by": check["checked_by"], "checked_at": check["checked_at"],
        "query_sha256": exchange["query_sha256"], "response_sha256": exchange["response_sha256"],
        "adoption_status": adopted, "purpose": record["purpose"], "purpose_confirmed": True}
    if any(proof.get(key) != value for key, value in expected.items()):
        raise ValueError("Human evidence does not bind the reviewed query, response and purpose")
    if exchange["assistant_event_seqs"] and not exchange["models"]:
        raise ValueError("Actual model is missing for a reviewed interaction")
    if adopted == "adopted":
        if not exchange["response"].strip():
            raise ValueError("Adopted interaction has no visible assistant text")
        if record.get("citations_verified") is not True or proof.get("citations_verified") is not True or not record.get("citation_evidence"):
            raise ValueError("Adopted use needs human-checked citation evidence or an evidenced not-applicable rationale")
        for ref in record["citation_evidence"]:
            path = checked_reference(project, ref)
            if path.stat().st_size == 0:
                raise ValueError("Citation evidence cannot be empty")
        checks = {r.get("attachment_id"): r for r in record.get("attachment_checks", []) if isinstance(r, dict)}
        for identity in exchange["attachment_ids"]:
            ref = checks.get(identity)
            if not ref or ref.get("checked_by") != check["checked_by"]:
                raise ValueError("Adopted attachment reference needs an independently preserved original and human check")
            checked_reference(project, ref)
    return adopted


_ESCAPES = {"\\": r"\textbackslash{}", "{": r"\{", "}": r"\}", "$": r"\$", "&": r"\&",
            "#": r"\#", "%": r"\%", "_": r"\_", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}


def latex_text(value):
    return "".join(_ESCAPES.get(char, char) for char in str(value))


def latex_block(value):
    # Literal escaping prevents \end{quote}, %, or other query text executing as
    # TeX. Explicit space/line tokens preserve code indentation without minted.
    lines = []
    for line in value.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = line.expandtabs(4)
        escaped = "".join(r"\hspace*{0.5em}\allowbreak{}" if c == " " else latex_text(c) for c in line)
        lines.append((escaped or r"\mbox{}") + r"\par\noindent")
    return "\n".join([r"\begin{quote}\small\ttfamily\raggedright", *lines, r"\end{quote}"])


def build_report(project, archives, human_uses=None, final=False):
    project = Path(project).resolve()
    sessions, provenance, warnings = load_archives(archives)
    exchanges, extraction_warnings = extract_exchanges(sessions)
    warnings.extend(extraction_warnings)
    if not exchanges:
        warnings.append("No visible user-role query/assistant exchanges are available")
    human_rows = []
    if human_uses:
        payload = read_json(human_uses)
        human_rows = payload.get("records") if isinstance(payload, dict) and payload.get("format_version") == 1 else None
        if not isinstance(human_rows, list):
            raise ValueError("Human-use file must be {format_version:1,records:[...]}")
    by_key = {}
    for record in human_rows:
        if not isinstance(record, dict):
            raise ValueError("Human-use records must be objects")
        key = (record.get("session_id"), record.get("query_event_seq"))
        if key in by_key:
            raise ValueError("Duplicate human-use record for one query")
        by_key[key] = record
    known_keys = {(e["session_id"], e["query_event_seq"]) for e in exchanges}
    if set(by_key) - known_keys:
        raise ValueError("Human-use record refers to an unarchived query")
    if final and warnings:
        raise ValueError("Final report refused: " + "; ".join(warnings))
    included, coverage = [], []
    for exchange in exchanges:
        record = by_key.get((exchange["session_id"], exchange["query_event_seq"]))
        state = "pending"
        if final:
            state = check_use(project, exchange, record)
        if not final or state == "adopted":
            included.append((exchange, record, state))
        coverage.append({key: exchange[key] for key in ("session_id", "role_preset", "query_event_seq",
            "assistant_event_seqs", "query_sha256", "response_sha256", "models", "attachment_ids")}
            | {"review_state": state, "record_id": record.get("record_id") if record else None,
               "source_refs": exchange["archive_refs"]})
    lines = ["% Generated by scripts/ai_report.py; body fragment for the parent Report on Use of AI Tools section.",
             "% Preserve original Unicode queries: the parent XeLaTeX preamble must load xeCJK and a CJK main/mono font."]
    if not final:
        lines.append(r"\noindent\textbf{DRAFT -- HUMAN VERIFICATION PENDING. NOT A SUBMISSION APPROVAL.}\par")
    lines.extend([
        r"\noindent This report covers filtered visible user-role queries and their complete corresponding visible assistant text at recorded archive cutoffs. User-role queries may be delegated agent tasks, not statements authored by a person. System/developer instructions, tool-return dumps and hidden reasoning are outside the report.\par",
        r"\noindent Attachment archives contain references only. Original attachments require separate preservation and checking. Recorded model labels identify the actual visible provider/model routes; no unrecorded version is inferred.\par",
        r"\noindent File consistency checks do not authenticate human identity or establish scientific truth. The team remains responsible for the applicable contest policy, citation verification and final submission.\par",
        f"\\noindent Archives: {len(provenance)}; sessions: {len(sessions)}; visible interactions: {len(exchanges)}; included below: {len(included)}.\\par",
    ])
    if final:
        lines.append(f"\\noindent Reviewed interactions not adopted: {len(exchanges)-len(included)}; their event references remain in the coverage index.\\par")
    if warnings:
        lines.append(r"\subsection*{Draft coverage limitations}")
        for item in warnings:
            lines.append(latex_text(item) + r"\par")
    for number, (exchange, record, state) in enumerate(included, 1):
        label = f"{exchange['session_id']} / query event {exchange['query_event_seq']}"
        lines.append(f"\\subsection*{{{number}. {latex_text(label)}}}")
        model_label = "; ".join(f"{m['provider']} / {m['model']}" for m in exchange["models"])
        if not model_label:
            model_label = "UNKNOWN -- requires review" if exchange["assistant_event_seqs"] else "No assistant response at this cutoff; no model invocation associated"
        lines.append("\\noindent Role: " + latex_text(exchange["role_preset"] or "unknown") + r"\par")
        lines.append("\\noindent Actual model route(s): " + latex_text(model_label) + r"\par")
        purpose = record.get("purpose") if record else "Not recorded -- human use review required"
        lines.append("\\noindent Purpose: " + latex_text(purpose) + r"\par")
        lines.append("\\noindent Review state: " + latex_text(state) + r"\par")
        lines.append("\\noindent Source assistant event(s): " + latex_text(", ".join(map(str, exchange["assistant_event_seqs"])) or "none at this cutoff") + r"\par")
        lines.append("\\noindent Query SHA-256: " + latex_text(exchange["query_sha256"]) + r"\par")
        lines.append("\\noindent Response SHA-256: " + latex_text(exchange["response_sha256"]) + r"\par")
        lines.extend([r"\paragraph{Visible query (exact archived text)}", latex_block(exchange["query"]),
                      r"\paragraph{Corresponding visible assistant text (complete at cutoff)}", latex_block(exchange["response"])])
        if exchange["attachment_ids"]:
            lines.append("\\noindent Attachment references: " + latex_text(", ".join(exchange["attachment_ids"])) + r". Bytes are not part of the transcript archive.\par")
    metadata = {"format_version": 1, "status": "final_from_supplied_human_records" if final else "draft",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "human_identity_authenticated": False, "official_submission_approved": False,
        "archives": provenance, "sessions": len(sessions), "interactions": coverage,
        "included_interactions": len(included), "warnings": warnings,
        "coverage": "visible text only; no system/developer prompts, tool-return dumps, hidden reasoning or attachment bytes",
        "human_use_file": str(Path(human_uses).resolve()) if human_uses else None,
        "human_use_sha256": sha256_bytes(Path(human_uses).read_bytes()) if human_uses else None}
    return "\n\n".join(lines) + "\n", metadata


def save_report(project, output, text, metadata):
    project = Path(project).resolve()
    path = relative_file(project, output)
    if path.is_relative_to(project / "data/raw"):
        raise ValueError("Report cannot be written under immutable raw inputs")
    coverage = path.with_suffix(".coverage.json")
    if path.exists() or coverage.exists():
        raise ValueError("Report outputs already exist; choose a new versioned --output path")
    path.parent.mkdir(parents=True, exist_ok=True)
    metadata = {**metadata, "report_path": path.relative_to(project).as_posix(), "report_sha256": text_hash(text)}
    # Exclusive creation is intentional: never replace an earlier reviewed draft.
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(text)
    try:
        with coverage.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(metadata, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return {"ok": True, "status": metadata["status"], "report": str(path), "coverage": str(coverage),
        "included_interactions": metadata["included_interactions"], "warnings": metadata["warnings"],
        "official_submission_approved": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--archive", type=Path, action="append", required=True,
                        help="Audit directory; repeat for multiple immutable checkpoints")
    parser.add_argument("--human-uses", type=Path)
    parser.add_argument("--output", default="paper/ai-use/report-v1.tex", help="New project-relative versioned .tex output; choose v2 on a later run")
    parser.add_argument("--final", action="store_true", help="Require complete archives and supplied real human-use/citation evidence")
    args = parser.parse_args(argv)
    try:
        if not (args.root / ".mcm-project").is_dir():
            raise ValueError("Project root needs the .mcm-project directory marker")
        project = args.root.resolve()
        archives = [path if path.is_absolute() else project / path for path in args.archive]
        uses = args.human_uses
        if uses and not uses.is_absolute():
            uses = project / uses
        text, metadata = build_report(project, archives, uses, args.final)
        result = save_report(args.root, args.output, text, metadata)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
