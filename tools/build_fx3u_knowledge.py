#!/usr/bin/env python3
"""Build the offline FX3U manual knowledge database.

This is an offline build tool.  ``pypdf`` is required only while rebuilding
the database; readers of the generated SQLite file need only Python's standard
``sqlite3`` module (or any SQLite client with FTS5 support).
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
import time
import unicodedata

try:
    import pypdf
    from pypdf import PdfReader
except ImportError as error:  # pragma: no cover - exercised by build machines
    raise SystemExit(
        "pypdf is required only to build the index. Install it with "
        "`python -m pip install pypdf`, then rerun this script."
    ) from error


BUILDER_VERSION = "1.1.0"
SCHEMA_VERSION = 2
MANUAL_NUMBER = "JY997D19401"
MANUAL_REVISION = "F"
MANUAL_TITLE = (
    "FX3G·FX3U·FX3UC系列微型可编程控制器 "
    "编程手册[基本·应用指令说明书]"
)
PLC_MODELS = "FX3G,FX3U,FX3UC"
TASK_TYPES = "*"

DEFAULT_TARGET_CHARS = 1800
DEFAULT_MAX_CHARS = 2600

CJK_RUN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+")
FNC_RE = re.compile(r"(?<![A-Z0-9])FNC\s*0*(\d{1,3})(?!\d)", re.IGNORECASE)
FNC_OPCODE_RE = re.compile(
    r"FNC\s*0*\d{1,3}\s*[－—-]\s*([A-Z][A-Z0-9_]*)",
    re.IGNORECASE,
)

DEVICE_PREFIX = r"(?:ER|SM|SD|TS|TC|CS|CC|[XYMSTCDRVZPIN])"
BRACKET_DEVICE_RE = re.compile(
    rf"\[\s*({DEVICE_PREFIX})\s*\]\s*(\d+)", re.IGNORECASE
)
DEVICE_RE = re.compile(
    rf"(?<![A-Z0-9])({DEVICE_PREFIX})\s*(\d+)(?![A-Z0-9])",
    re.IGNORECASE,
)
DEVICE_RANGE_RE = re.compile(
    rf"(?<![A-Z0-9])({DEVICE_PREFIX})\s*(\d+)\s*"
    rf"(?:～|~|－|—|-)\s*(?:({DEVICE_PREFIX})\s*)?(\d+)(?![A-Z0-9])",
    re.IGNORECASE,
)

BASE_INSTRUCTIONS = {
    "LD", "LDI", "LDP", "LDF", "AND", "ANI", "ANDP", "ANDF",
    "OR", "ORI", "ORP", "ORF", "ANB", "ORB", "MPS", "MRD", "MPP",
    "OUT", "SET", "RST", "PLS", "PLF", "MC", "MCR", "INV", "NOP",
    "END", "FEND", "CJ", "CALL", "SRET", "IRET", "EI", "DI", "FOR",
    "NEXT", "MOV", "DMOV", "BMOV", "FMOV", "ZRST", "CMP", "ZCP",
    "ADD", "SUB", "MUL", "DIV", "INC", "DEC", "SFTL", "SFTLP",
    "SFR", "SFL", "WSFR", "WSFL", "RS", "RS2", "FROM", "TO", "PID",
    "PLSY", "DPLSY", "PLSR", "DPLSR", "PLSV", "DRVI", "DDRVI",
    "DRVA", "DDRVA", "DVIT", "ZRN", "DSZR", "HSCS", "HSCR", "HSZ",
    "SPD",
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[1]
    default_source = repo_root.parent / "FX3G.FX3U编程手册.pdf"
    if not default_source.is_file():
        candidates = sorted(repo_root.parent.glob("FX3G.FX3U*.pdf"))
        if candidates:
            default_source = candidates[0]

    parser = argparse.ArgumentParser(
        description="Extract the FX3G/FX3U manual into a deterministic SQLite FTS5 index."
    )
    parser.add_argument("--source", type=Path, default=default_source)
    parser.add_argument(
        "--output",
        type=Path,
        default=repo_root / "resources" / "knowledge" / "fx3u_knowledge.sqlite",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=repo_root / "resources" / "knowledge" / "manifest.json",
    )
    parser.add_argument("--target-chars", type=int, default=DEFAULT_TARGET_CHARS)
    parser.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS)
    parser.add_argument("--progress-every", type=int, default=25)
    args = parser.parse_args(argv)
    if args.target_chars < 256:
        parser.error("--target-chars must be at least 256")
    if args.max_chars < args.target_chars:
        parser.error("--max-chars must be >= --target-chars")
    if args.progress_every < 1:
        parser.error("--progress-every must be positive")
    return args


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFC", value or "")
    value = value.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
    value = value.replace("\u00a0", " ")
    return "\n".join(line.rstrip() for line in value.split("\n")).strip()


def split_complete_blocks(text: str, target_chars: int, max_chars: int) -> list[str]:
    """Split text without dropping or duplicating a single normalized character."""
    if not text:
        return [""]
    blocks: list[str] = []
    start = 0
    length = len(text)
    minimum = max(128, target_chars // 2)
    while length - start > max_chars:
        upper = min(length, start + max_chars)
        lower = min(upper, start + minimum)
        preferred = min(upper, start + target_chars)

        cut = -1
        for separator in ("\n\n", "\n", "。", "！", "？", "；", " "):
            candidate = text.rfind(separator, lower, upper)
            if candidate >= preferred or (cut < 0 and candidate >= lower):
                cut = candidate + len(separator)
                if candidate >= preferred:
                    break
        if cut <= start:
            cut = upper
        blocks.append(text[start:cut])
        start = cut
    blocks.append(text[start:])
    assert "".join(blocks) == text
    return blocks


def cjk_bigrams(text: str) -> tuple[str, int]:
    terms: list[str] = []
    for match in CJK_RUN_RE.finditer(text):
        run = match.group(0)
        terms.extend(run[index : index + 2] for index in range(len(run) - 1))
    return " ".join(terms), len(terms)


def flatten_outline(reader: PdfReader) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    sequence = 0

    def walk(items: list[object], depth: int) -> None:
        nonlocal sequence
        for item in items:
            if isinstance(item, list):
                walk(item, depth + 1)
                continue
            try:
                pdf_page = reader.get_destination_page_number(item) + 1
            except Exception:
                continue
            title = normalize_text(str(getattr(item, "title", item))).replace("\n", " ")
            if not title:
                continue
            entries.append(
                {
                    "pdf_page": pdf_page,
                    "depth": depth,
                    "title": title,
                    "sequence": sequence,
                }
            )
            sequence += 1

    outline = reader.outline
    if isinstance(outline, list):
        walk(outline, 0)
    entries.sort(key=lambda item: (int(item["pdf_page"]), int(item["sequence"])))
    return entries


def outline_page_map(
    page_count: int, entries: list[dict[str, object]]
) -> dict[int, tuple[str, str, str]]:
    result: dict[int, tuple[str, str, str]] = {}
    stack: list[str] = []
    cursor = 0
    for pdf_page in range(1, page_count + 1):
        while cursor < len(entries) and int(entries[cursor]["pdf_page"]) <= pdf_page:
            entry = entries[cursor]
            depth = int(entry["depth"])
            title = str(entry["title"])
            stack = stack[:depth]
            while len(stack) < depth:
                stack.append("")
            stack.append(title)
            cursor += 1
        nonempty = [item for item in stack if item]
        chapter = nonempty[0] if nonempty else "前置页"
        section = nonempty[-1] if nonempty else chapter
        result[pdf_page] = (chapter, section, " > ".join(nonempty))
    return result


def extract_printed_page(text: str, pdf_page: int, page_count: int) -> tuple[int | None, str]:
    for line in text.splitlines()[:6]:
        candidate = line.strip()
        if re.fullmatch(r"\d{1,4}", candidate):
            number = int(candidate)
            if 0 < number < 2000:
                return number, "extracted"
    # This edition has two unnumbered PDF cover pages before printed page 1.
    if 3 <= pdf_page < page_count:
        return pdf_page - 2, "offset_fallback"
    return None, "unavailable"


def instruction_vocabulary(outline_entries: list[dict[str, object]]) -> set[str]:
    vocabulary = set(BASE_INSTRUCTIONS)
    for entry in outline_entries:
        title = str(entry["title"]).upper()
        vocabulary.update(match.group(1).upper() for match in FNC_OPCODE_RE.finditer(title))
    return {
        token
        for token in vocabulary
        if re.fullmatch(r"[A-Z][A-Z0-9_]{1,15}", token)
        and token not in {"CPU", "PLC", "RUN", "STOP", "ON", "OFF", "FNC"}
    }


def compile_instruction_re(vocabulary: set[str]) -> re.Pattern[str]:
    alternatives = "|".join(
        re.escape(token) for token in sorted(vocabulary, key=lambda item: (-len(item), item))
    )
    return re.compile(rf"(?<![A-Z0-9_])(?:{alternatives})(?![A-Z0-9_])", re.IGNORECASE)


def extract_entities(
    text: str, instruction_re: re.Pattern[str]
) -> Counter[tuple[str, str]]:
    entities: Counter[tuple[str, str]] = Counter()

    for match in DEVICE_RANGE_RE.finditer(text):
        first_prefix = match.group(1).upper()
        first_number = match.group(2)
        second_prefix = (match.group(3) or first_prefix).upper()
        second_number = match.group(4)
        normalized = f"{first_prefix}{first_number}-{second_prefix}{second_number}"
        entities[(normalized, "device_range")] += 1

    for match in BRACKET_DEVICE_RE.finditer(text):
        entities[(f"{match.group(1).upper()}{match.group(2)}", "device")] += 1
    for match in DEVICE_RE.finditer(text):
        entities[(f"{match.group(1).upper()}{match.group(2)}", "device")] += 1

    for match in instruction_re.finditer(text):
        entities[(match.group(0).upper(), "instruction")] += 1
    for match in FNC_RE.finditer(text):
        entities[(f"FNC {int(match.group(1)):02d}", "fnc")] += 1
    return entities


def create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        PRAGMA foreign_keys = ON;
        PRAGMA user_version = 2;

        CREATE TABLE meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        ) WITHOUT ROWID;

        CREATE TABLE chunks (
            id INTEGER PRIMARY KEY,
            chunk_uid TEXT NOT NULL UNIQUE,
            manual_number TEXT NOT NULL,
            revision TEXT NOT NULL,
            manual_title TEXT NOT NULL,
            plc_models TEXT NOT NULL,
            task_types TEXT NOT NULL,
            source_file TEXT NOT NULL,
            pdf_page INTEGER NOT NULL CHECK (pdf_page > 0),
            printed_page INTEGER,
            printed_page_source TEXT NOT NULL,
            chapter TEXT NOT NULL,
            section TEXT NOT NULL,
            outline_path TEXT NOT NULL,
            block_index INTEGER NOT NULL CHECK (block_index > 0),
            block_count INTEGER NOT NULL CHECK (block_count > 0),
            page_char_count INTEGER NOT NULL CHECK (page_char_count >= 0),
            page_text_sha256 TEXT NOT NULL,
            text TEXT NOT NULL,
            char_count INTEGER NOT NULL CHECK (char_count >= 0),
            text_sha256 TEXT NOT NULL,
            entities TEXT NOT NULL,
            entities_json TEXT NOT NULL,
            cjk_bigrams TEXT NOT NULL,
            UNIQUE (pdf_page, block_index)
        );

        CREATE TABLE entity_index (
            entity_norm TEXT NOT NULL,
            entity TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            plc_models TEXT NOT NULL,
            task_types TEXT NOT NULL,
            chunk_id INTEGER NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
            occurrences INTEGER NOT NULL CHECK (occurrences > 0),
            PRIMARY KEY (entity_norm, entity_type, chunk_id)
        ) WITHOUT ROWID;

        CREATE INDEX idx_chunks_pdf_page ON chunks(pdf_page, block_index);
        CREATE INDEX idx_chunks_printed_page ON chunks(printed_page);
        CREATE INDEX idx_chunks_chapter ON chunks(chapter, section);
        CREATE INDEX idx_entity_chunk ON entity_index(chunk_id);
        CREATE INDEX idx_entity_type_norm ON entity_index(entity_type, entity_norm);

        CREATE VIRTUAL TABLE chunks_fts USING fts5(
            text,
            cjk_bigrams,
            entities,
            chapter,
            section,
            content='chunks',
            content_rowid='id',
            tokenize='unicode61 remove_diacritics 0'
        );
        """
    )


def put_meta(connection: sqlite3.Connection, values: dict[str, object]) -> None:
    connection.executemany(
        "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
        [
            (
                key,
                json.dumps(value, ensure_ascii=False, sort_keys=True)
                if isinstance(value, (dict, list, bool))
                else str(value),
            )
            for key, value in sorted(values.items())
        ],
    )


def verify_database(
    database_path: Path,
    *,
    expected_pages: int,
    expected_chars: int,
    page_digests: dict[int, tuple[int, str]],
) -> dict[str, object]:
    connection = sqlite3.connect(f"file:{database_path.as_posix()}?mode=ro", uri=True)
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError(f"SQLite integrity_check failed: {integrity}")
        chunk_count = int(connection.execute("SELECT COUNT(*) FROM chunks").fetchone()[0])
        distinct_pages = int(
            connection.execute("SELECT COUNT(DISTINCT pdf_page) FROM chunks").fetchone()[0]
        )
        total_chars = int(
            connection.execute("SELECT COALESCE(SUM(char_count), 0) FROM chunks").fetchone()[0]
        )
        fts_count = int(connection.execute("SELECT COUNT(*) FROM chunks_fts").fetchone()[0])
        entity_rows = int(connection.execute("SELECT COUNT(*) FROM entity_index").fetchone()[0])
        unique_entities = int(
            connection.execute("SELECT COUNT(DISTINCT entity_norm) FROM entity_index").fetchone()[0]
        )
        orphan_entities = int(
            connection.execute(
                "SELECT COUNT(*) FROM entity_index e LEFT JOIN chunks c "
                "ON c.id=e.chunk_id WHERE c.id IS NULL"
            ).fetchone()[0]
        )
        out_of_scope_chunks = int(
            connection.execute(
                "SELECT COUNT(*) FROM chunks WHERE plc_models<>? OR task_types<>?",
                (PLC_MODELS, TASK_TYPES),
            ).fetchone()[0]
        )
        out_of_scope_entities = int(
            connection.execute(
                "SELECT COUNT(*) FROM entity_index WHERE plc_models<>? OR task_types<>?",
                (PLC_MODELS, TASK_TYPES),
            ).fetchone()[0]
        )
        if distinct_pages != expected_pages:
            raise RuntimeError(
                f"page coverage mismatch: expected {expected_pages}, got {distinct_pages}"
            )
        if total_chars != expected_chars:
            raise RuntimeError(
                f"character coverage mismatch: expected {expected_chars}, got {total_chars}"
            )
        if fts_count != chunk_count:
            raise RuntimeError(f"FTS row mismatch: chunks={chunk_count}, fts={fts_count}")
        if orphan_entities:
            raise RuntimeError(f"entity_index has {orphan_entities} orphan rows")
        if out_of_scope_chunks or out_of_scope_entities:
            raise RuntimeError(
                "scope metadata mismatch: "
                f"chunks={out_of_scope_chunks}, entities={out_of_scope_entities}"
            )

        for pdf_page, (page_chars, page_sha256) in page_digests.items():
            rows = connection.execute(
                "SELECT text FROM chunks WHERE pdf_page=? ORDER BY block_index", (pdf_page,)
            ).fetchall()
            reconstructed = "".join(row[0] for row in rows)
            if len(reconstructed) != page_chars:
                raise RuntimeError(f"page {pdf_page} character reconstruction failed")
            if hashlib.sha256(reconstructed.encode("utf-8")).hexdigest() != page_sha256:
                raise RuntimeError(f"page {pdf_page} SHA-256 reconstruction failed")

        probe_hits: dict[str, int] = {}
        for probe in ("M8029", "DRVI", "高速 计数"):
            try:
                probe_hits[probe] = int(
                    connection.execute(
                        "SELECT COUNT(*) FROM chunks_fts WHERE chunks_fts MATCH ?", (probe,)
                    ).fetchone()[0]
                )
            except sqlite3.OperationalError:
                probe_hits[probe] = 0
        entity_probe_hits = {
            entity: int(
                connection.execute(
                    "SELECT COUNT(*) FROM entity_index "
                    "WHERE entity_norm=? AND plc_models=?",
                    (entity.casefold(), PLC_MODELS),
                ).fetchone()[0]
            )
            for entity in ("M8029", "DRVI")
        }
        if entity_probe_hits["M8029"] < 1:
            raise RuntimeError("normalized entity probe M8029 was not indexed")
        return {
            "integrity_check": integrity,
            "chunk_count": chunk_count,
            "distinct_pdf_pages": distinct_pages,
            "total_characters": total_chars,
            "fts_rows": fts_count,
            "entity_rows": entity_rows,
            "unique_entities": unique_entities,
            "orphan_entities": orphan_entities,
            "scope_metadata": "ok",
            "page_reconstruction": "ok",
            "fts_probe_hits": probe_hits,
            "entity_probe_hits": entity_probe_hits,
        }
    finally:
        connection.close()


def atomic_write_json(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
        os.replace(temporary_path, path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def build(args: argparse.Namespace) -> dict[str, object]:
    started = time.perf_counter()
    source = args.source.expanduser().resolve()
    output = args.output.expanduser().resolve()
    manifest_path = args.manifest.expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"source manual not found: {source}")
    if source == output or source == manifest_path or output == manifest_path:
        raise ValueError("source, database output, and manifest must be distinct files")
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    source_sha256 = sha256_file(source)
    reader = PdfReader(str(source))
    page_count = len(reader.pages)
    outline_entries = flatten_outline(reader)
    page_outline = outline_page_map(page_count, outline_entries)
    instruction_re = compile_instruction_re(instruction_vocabulary(outline_entries))

    file_handle, temporary_name = tempfile.mkstemp(
        prefix=".fx3u_knowledge-", suffix=".sqlite.tmp", dir=output.parent
    )
    os.close(file_handle)
    temporary_db = Path(temporary_name)
    temporary_db.unlink(missing_ok=True)

    build_timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    stats = Counter()
    page_digests: dict[int, tuple[int, str]] = {}
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(temporary_db)
        connection.execute("PRAGMA journal_mode=OFF")
        connection.execute("PRAGMA synchronous=OFF")
        connection.execute("PRAGMA temp_store=MEMORY")
        connection.execute("PRAGMA page_size=4096")
        create_schema(connection)
        put_meta(
            connection,
            {
                "schema_version": SCHEMA_VERSION,
                "builder_version": BUILDER_VERSION,
                "built_at_utc": build_timestamp,
                "manual_number": MANUAL_NUMBER,
                "revision": MANUAL_REVISION,
                "manual_title": MANUAL_TITLE,
                "plc_models": PLC_MODELS,
                "task_types": TASK_TYPES,
                "source_file": source.name,
                "source_sha256": source_sha256,
                "source_bytes": source.stat().st_size,
                "pdf_page_count": page_count,
                "printed_page_offset": 2,
                "pypdf_version": pypdf.__version__,
                "target_chars": args.target_chars,
                "max_chars": args.max_chars,
                "runtime_dependencies": ["SQLite with FTS5"],
            },
        )

        for page_index, page in enumerate(reader.pages, start=1):
            extracted = page.extract_text() or ""
            text = normalize_text(extracted)
            blocks = split_complete_blocks(text, args.target_chars, args.max_chars)
            chapter, section, outline_path = page_outline[page_index]
            printed_page, printed_source = extract_printed_page(text, page_index, page_count)
            page_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
            page_digests[page_index] = (len(text), page_sha256)
            stats["pages"] += 1
            stats["pages_with_text"] += int(bool(text))
            stats["characters"] += len(text)

            for block_index, block in enumerate(blocks, start=1):
                entity_counts = extract_entities(block, instruction_re)
                entity_tokens = sorted({entity for (entity, _kind) in entity_counts})
                entity_json = [
                    {"entity": entity, "type": kind, "occurrences": count}
                    for (entity, kind), count in sorted(entity_counts.items())
                ]
                bigram_text, bigram_count = cjk_bigrams(block)
                chunk_uid = (
                    f"{MANUAL_NUMBER}{MANUAL_REVISION}:"
                    f"p{page_index:04d}:b{block_index:03d}"
                )
                cursor = connection.execute(
                    """
                    INSERT INTO chunks(
                        chunk_uid, manual_number, revision, manual_title,
                        plc_models, task_types, source_file,
                        pdf_page, printed_page, printed_page_source,
                        chapter, section, outline_path, block_index, block_count,
                        page_char_count, page_text_sha256,
                        text, char_count, text_sha256, entities, entities_json,
                        cjk_bigrams
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        chunk_uid,
                        MANUAL_NUMBER,
                        MANUAL_REVISION,
                        MANUAL_TITLE,
                        PLC_MODELS,
                        TASK_TYPES,
                        source.name,
                        page_index,
                        printed_page,
                        printed_source,
                        chapter,
                        section,
                        outline_path,
                        block_index,
                        len(blocks),
                        len(text),
                        page_sha256,
                        block,
                        len(block),
                        hashlib.sha256(block.encode("utf-8")).hexdigest(),
                        " ".join(entity_tokens),
                        json.dumps(entity_json, ensure_ascii=False, separators=(",", ":")),
                        bigram_text,
                    ),
                )
                chunk_id = int(cursor.lastrowid)
                connection.executemany(
                    """
                    INSERT INTO entity_index(
                        entity_norm, entity, entity_type, plc_models, task_types,
                        chunk_id, occurrences
                    ) VALUES (?,?,?,?,?,?,?)
                    """,
                    [
                        (
                            entity.casefold(), entity, kind, PLC_MODELS, TASK_TYPES,
                            chunk_id, count,
                        )
                        for (entity, kind), count in sorted(entity_counts.items())
                    ],
                )
                stats["chunks"] += 1
                stats["entity_rows"] += len(entity_counts)
                stats["entity_occurrences"] += sum(entity_counts.values())
                stats["cjk_bigrams"] += bigram_count

            if page_index % args.progress_every == 0 or page_index == page_count:
                elapsed = time.perf_counter() - started
                print(
                    f"[{page_index:04d}/{page_count:04d}] "
                    f"chunks={stats['chunks']} chars={stats['characters']} "
                    f"elapsed={elapsed:.1f}s",
                    flush=True,
                )

        connection.execute("INSERT INTO chunks_fts(chunks_fts) VALUES('rebuild')")
        unique_entities = int(
            connection.execute("SELECT COUNT(DISTINCT entity_norm) FROM entity_index").fetchone()[0]
        )
        stats["unique_entities"] = unique_entities
        elapsed_before_finalize = time.perf_counter() - started
        put_meta(
            connection,
            {
                "chunk_count": stats["chunks"],
                "pages_with_text": stats["pages_with_text"],
                "total_characters": stats["characters"],
                "entity_index_rows": stats["entity_rows"],
                "unique_entities": stats["unique_entities"],
                "cjk_bigram_occurrences": stats["cjk_bigrams"],
                "build_duration_seconds_before_vacuum": round(elapsed_before_finalize, 3),
            },
        )
        connection.commit()
        connection.execute("ANALYZE")
        connection.commit()
        connection.execute("VACUUM")
        connection.close()
        connection = None
        os.replace(temporary_db, output)
    except Exception:
        if connection is not None:
            connection.close()
        temporary_db.unlink(missing_ok=True)
        raise

    verification = verify_database(
        output,
        expected_pages=page_count,
        expected_chars=stats["characters"],
        page_digests=page_digests,
    )
    duration_seconds = time.perf_counter() - started
    database_sha256 = sha256_file(output)
    manifest: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "database": {
            "file": output.name,
            "bytes": output.stat().st_size,
            "sha256": database_sha256,
            "tables": ["meta", "chunks", "entity_index", "chunks_fts"],
            "runtime_dependencies": ["SQLite with FTS5"],
        },
        "manual": {
            "title": MANUAL_TITLE,
            "manual_number": MANUAL_NUMBER,
            "revision": MANUAL_REVISION,
            "source_file": source.name,
            "source_bytes": source.stat().st_size,
            "source_sha256": source_sha256,
            "pdf_pages": page_count,
            "printed_page_offset": 2,
        },
        "build": {
            "builder": Path(__file__).name,
            "builder_version": BUILDER_VERSION,
            "built_at_utc": build_timestamp,
            "duration_seconds": round(duration_seconds, 3),
            "pypdf_version": pypdf.__version__,
            "target_chars": args.target_chars,
            "max_chars": args.max_chars,
        },
        "statistics": {
            "pdf_pages": stats["pages"],
            "pages_with_text": stats["pages_with_text"],
            "chunks": stats["chunks"],
            "characters": stats["characters"],
            "entity_index_rows": stats["entity_rows"],
            "entity_occurrences": stats["entity_occurrences"],
            "unique_entities": stats["unique_entities"],
            "cjk_bigram_occurrences": stats["cjk_bigrams"],
        },
        "verification": verification,
    }
    atomic_write_json(manifest_path, manifest)
    print(
        f"Built {output} ({output.stat().st_size} bytes) in {duration_seconds:.1f}s",
        flush=True,
    )
    print(f"Manifest: {manifest_path}", flush=True)
    return manifest


def main(argv: list[str] | None = None) -> int:
    """Compatibility entry point for the schema-v3 multi-manual builder."""

    from build_fx3u_knowledge_v3 import main as build_v3

    return build_v3(argv)


if __name__ == "__main__":
    raise SystemExit(main())
