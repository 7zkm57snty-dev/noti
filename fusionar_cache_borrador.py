#!/usr/bin/env python3
"""Reaplica el borrador editorial sobre la versión más reciente de cache.json."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


MISSING = object()


def merge_changed_fields(base: dict[str, Any], draft: dict[str, Any], current: dict[str, Any]) -> None:
    """Aplica cambios locales solo cuando el valor remoto aún coincide con la base."""
    for key in set(base) | set(draft):
        old = base.get(key, MISSING)
        local = draft.get(key, MISSING)
        remote = current.get(key, MISSING)
        if local == old:
            continue
        if remote == old:
            if local is MISSING:
                current.pop(key, None)
            else:
                current[key] = local


def merge_cache(base: dict[str, Any], draft: dict[str, Any], current: dict[str, Any]) -> tuple[int, int]:
    """Une altas/ediciones locales con los cambios concurrentes que ya llegaron a main."""
    added = 0
    updated = 0
    for field in ("noticias", "breves"):
        base_items = base.get(field, []) or []
        draft_items = draft.get(field, []) or []
        current_items = current.get(field, []) or []
        base_by_id = {
            str(item.get("id")): item
            for item in base_items
            if isinstance(item, dict) and item.get("id")
        }
        current_by_id = {
            str(item.get("id")): item
            for item in current_items
            if isinstance(item, dict) and item.get("id")
        }
        new_items: list[dict[str, Any]] = []
        for local in draft_items:
            if not isinstance(local, dict) or not local.get("id"):
                continue
            key = str(local["id"])
            if key not in base_by_id:
                if key not in current_by_id:
                    new_items.append(local)
                    added += 1
                continue
            remote = current_by_id.get(key)
            if remote is None:
                # Una noticia retirada remotamente no se restaura desde un borrador antiguo.
                continue
            before = json.dumps(remote, ensure_ascii=False, sort_keys=True)
            merge_changed_fields(base_by_id[key], local, remote)
            after = json.dumps(remote, ensure_ascii=False, sort_keys=True)
            if after != before:
                updated += 1
        current[field] = new_items + current_items

    # Conserva campos editoriales de nivel superior sin sobrescribir cambios remotos.
    merge_changed_fields(
        {key: value for key, value in base.items() if key not in ("noticias", "breves")},
        {key: value for key, value in draft.items() if key not in ("noticias", "breves")},
        current
    )
    return added, updated


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--draft", required=True, type=Path)
    parser.add_argument("--target", required=True, type=Path)
    args = parser.parse_args()

    base = json.loads(args.base.read_text(encoding="utf-8"))
    draft = json.loads(args.draft.read_text(encoding="utf-8"))
    current = json.loads(args.target.read_text(encoding="utf-8"))

    # La base para la siguiente sincronización pasa a ser la versión remota actual,
    # no el borrador local que todavía debe convertirse en una propuesta.
    args.base.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    added, updated = merge_cache(base, draft, current)
    args.target.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Borrador reaplicado sin publicar: {added} noticias nuevas y {updated} registros editados.")
    

if __name__ == "__main__":
    main()
