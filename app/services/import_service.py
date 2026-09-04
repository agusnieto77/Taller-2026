from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from datetime import date
from typing import Any


class ImportValidationError(ValueError):
    pass


@dataclass(frozen=True)
class NotePayload:
    external_id: str
    position: int
    title: str
    text: str
    published_at: date | None = None
    outlet: str | None = None
    url: str | None = None
    section: str | None = None
    metadata_json: dict[str, Any] | None = None


def _error(row: int, field: str, message: str) -> ImportValidationError:
    return ImportValidationError(f"fila {row}, campo {field}: {message}")


def _records(filename: str, content: bytes) -> list[dict[str, Any]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ImportValidationError("archivo: UTF-8 inválido") from exc
    suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if suffix == "json":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ImportValidationError(f"archivo: JSON inválido ({exc.msg})") from exc
        if isinstance(data, dict):
            data = data.get("notes")
        if not isinstance(data, list):
            raise ImportValidationError("archivo: se esperaba un arreglo JSON o un objeto con notes")
        return data
    if suffix == "csv":
        try:
            return list(csv.DictReader(io.StringIO(text)))
        except csv.Error as exc:
            raise ImportValidationError(f"archivo: CSV inválido ({exc})") from exc
    raise ImportValidationError("archivo: extensión no soportada; use .json o .csv")


def parse_notes_upload(filename: str, content: bytes) -> list[NotePayload]:
    records = _records(filename, content)
    if not records:
        raise ImportValidationError("archivo: no contiene notas")
    result: list[NotePayload] = []
    ids: set[str] = set()
    positions: set[int] = set()
    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            raise _error(index, "nota", "debe ser un objeto")
        def required(name: str, alias: str | None = None) -> str:
            key = alias or name
            value = record.get(key)
            if value is None or not str(value).strip():
                raise _error(index, name, "es obligatorio")
            return str(value).strip()
        external_id = required("id")
        if external_id in ids:
            raise _error(index, "id", "id duplicado")
        ids.add(external_id)
        title = required("titulo")
        text = required("texto")
        raw_position = record.get("position", index)
        try:
            position = int(raw_position)
        except (TypeError, ValueError) as exc:
            raise _error(index, "position", "debe ser un entero") from exc
        if position < 1:
            raise _error(index, "position", "debe ser mayor o igual a 1")
        if position in positions:
            raise _error(index, "position", "posición duplicada")
        positions.add(position)
        raw_date = record.get("fecha")
        published_at = None
        if raw_date not in (None, ""):
            try:
                published_at = date.fromisoformat(str(raw_date).strip())
            except ValueError as exc:
                raise _error(index, "fecha", "debe ser una fecha ISO válida") from exc
        metadata = record.get("metadata")
        if isinstance(metadata, str) and metadata.strip():
            try:
                metadata = json.loads(metadata)
            except json.JSONDecodeError as exc:
                raise _error(index, "metadata", "JSON inválido") from exc
        if metadata is not None and not isinstance(metadata, dict):
            raise _error(index, "metadata", "debe ser un objeto JSON")
        result.append(NotePayload(external_id, position, title, text, published_at, _optional(record.get("medio")), _optional(record.get("url")), _optional(record.get("seccion")), metadata))
    return sorted(result, key=lambda item: item.position)


def _optional(value: Any) -> str | None:
    if value is None or not str(value).strip():
        return None
    return str(value).strip()
