#!/usr/bin/env python3
"""Persist intent-classifier results to ``intent_inbox`` + ``classifier_audit``.

WHY THIS EXISTS
---------------
The classifier's write-back used to be inline SQL:

    UPDATE intent_inbox SET ... classifier_output='<full JSON>' WHERE id=...;
    INSERT INTO classifier_audit (... entities, reasoning, ...) VALUES ('...');

Every single-quoted slot carried message-derived text — ``classifier_output``,
``entities``, ``reasoning``, ``would_have_done`` all echo the original message.
Roughly every other Slack message contains an apostrophe ("let's ship", "I'm
done"), which closes the SQL string early: the UPDATE fails with a syntax error
(so the row never gets marked ``processed=1`` and re-loops), and a crafted
apostrophe payload can inject. This script takes the classifier's structured
result on stdin and writes both tables via **bound parameters** — no escaping,
no injection, apostrophes and quotes stored verbatim.

INPUT (stdin): a JSON array (or single object) of classified rows::

    [ { "id": <intent_inbox id>, "intent": "<primary intent>",
        "confidence": <float>, "classifier_output": {<full result obj>},
        "secondary_intents": ["..."], "entities": {...},
        "reasoning": "<one sentence>", "would_have_done": "<one clause>" }, ... ]

``classifier_output`` may be an object (it is re-serialized) or a string (stored
as-is). Missing optional fields default sanely.

USAGE
-----
    python3 /opt/lib/write_classification.py [db_path] <<'JSONEOF'
    [ { ... } ]
    JSONEOF

The quoted heredoc (``<<'JSONEOF'``) feeds the JSON to stdin literally, so the
apostrophes/quotes/newlines in the payload never hit shell expansion either.
"""
import sys
import re
import json
import sqlite3

DEFAULT_DB = "/data/queue/alaska.db"

_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")  # strip C0 controls incl NUL; keep \t \n \r


def clean(value):
    return value if value is None else _CTRL.sub("", value)


def _as_json_text(value, default):
    """Serialize dict/list to JSON text; pass through an existing string."""
    if value is None:
        value = default
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def write_rows(rows, db_path=DEFAULT_DB):
    """Mark each classified row processed and write its audit record. Returns count."""
    written = 0
    con = sqlite3.connect(db_path)
    try:
        con.execute("PRAGMA foreign_keys=ON")
        for row in rows:
            rid = row["id"]
            intent = clean(row["intent"])
            confidence = float(row.get("confidence", 0.0))
            classifier_output = clean(_as_json_text(row.get("classifier_output", row), "{}"))
            con.execute(
                "UPDATE intent_inbox SET processed=1, intent=?, confidence=?, "
                "classifier_output=?, processed_at=CURRENT_TIMESTAMP WHERE id=?",
                (intent, confidence, classifier_output, rid),
            )
            con.execute(
                "INSERT INTO classifier_audit "
                "(inbox_id, intent, secondary_intents, confidence, entities, reasoning, would_have_done) "
                "VALUES (?,?,?,?,?,?,?)",
                (
                    rid,
                    intent,
                    clean(_as_json_text(row.get("secondary_intents", []), "[]")),
                    confidence,
                    clean(_as_json_text(row.get("entities", {}), "{}")),
                    clean(row.get("reasoning", "")),
                    clean(row.get("would_have_done", "")),
                ),
            )
            written += 1
        con.commit()
    finally:
        con.close()
    return written


def main(argv):
    db_path = argv[1] if len(argv) > 1 else DEFAULT_DB
    payload = json.load(sys.stdin)
    if isinstance(payload, dict):
        payload = [payload]
    written = write_rows(payload, db_path)
    print(f"write_classification: wrote {written} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
