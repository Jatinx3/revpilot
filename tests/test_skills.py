"""Skill-pack structural tests (Phase 3) — no LLM calls.

Covers tests/SKILL_TEST_SCENARIOS.md: pack version pin, minimum count, judgment
skills (threshold + action), tool routing, distinctness, adversarial guardrail,
and the OTA/block concentration bonus.
"""

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"
REQUIRED_TOOLS = (
    "get_otb_summary", "get_segment_mix", "get_pickup_delta",
    "get_as_of_otb", "get_block_vs_transient_mix",
)


def _skill_files():
    """All skill files: every */SKILL.md plus the CHALLENGE_SKILL.md pack pin."""
    files = sorted(SKILLS.glob("**/SKILL.md"))
    files.append(SKILLS / "CHALLENGE_SKILL.md")
    return files


def _split(path):
    """Split a skill file into (frontmatter, body); assert it has YAML frontmatter."""
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.S)
    assert m, f"{path} missing YAML frontmatter"
    return m.group(1), m.group(2)


def _field(frontmatter, key):
    """Read a single `key: value` field from YAML frontmatter."""
    m = re.search(rf"^{key}:\s*(.+)$", frontmatter, re.M)
    return m.group(1).strip() if m else None


# Scenario 1 — pack version pin
def test_pack_version_pin():
    fm, _ = _split(SKILLS / "CHALLENGE_SKILL.md")
    assert "otel-rm-v2" in fm


# Scenario 2 — minimum skill count
def test_min_skill_count():
    skill_md = list(SKILLS.glob("**/SKILL.md"))
    assert len(skill_md) >= 6
    for p in _skill_files():
        fm, _ = _split(p)
        assert _field(fm, "name") and _field(fm, "description")


# Scenario 3 — judgment skills (threshold + action, >=80 words)
def test_judgment_skills():
    threshold = re.compile(r"(\d+%|0\.\d+|ADR\s+\w+\s+\d+)")
    action = re.compile(r"(recommend|shift|close|hold|review|protect|tighten|raise)", re.I)
    judged = 0
    for p in _skill_files():
        _, body = _split(p)
        if threshold.search(body) and action.search(body) and len(body.split()) >= 80:
            judged += 1
    assert judged >= 3, f"only {judged} judgment skills found"


# Scenario 4 — tool routing declared, no raw SQL
def test_each_skill_names_a_tool_and_no_raw_sql():
    for p in _skill_files():
        text = p.read_text(encoding="utf-8")
        assert any(tool in text for tool in REQUIRED_TOOLS), f"{p} names no required tool"
        assert "reservations_hackathon" not in text, f"{p} references the raw table"
        assert "run_sql" not in text, f"{p} references run_sql"


# Scenario 5 — distinct routing + coverage
def test_distinct_and_coverage():
    names, descs = set(), set()
    for p in _skill_files():
        fm, _ = _split(p)
        name = _field(fm, "name")
        desc = re.sub(r"\s+", " ", _field(fm, "description"))
        assert name not in names, f"duplicate name {name}"
        assert desc not in descs, "duplicate description"
        names.add(name)
        descs.add(desc)
    assert {"pickup-pace", "segment-mix", "otb-summary"} <= names


# Scenario 6 — adversarial guardrail present
def test_adversarial_guardrail():
    # Published S6 wants a skill that explicitly cautions against a known pitfall:
    # conflating stay rows with reservations, OR misusing property_date for monthly
    # analysis. Check the guardrail *content*, not an incidental word like "cancelled".
    bodies = [_split(p)[1].lower() for p in _skill_files()]
    rows_vs_reservations = any(
        "row" in b and "reservation" in b and ("are not" in b or "not reservation" in b
        or "distinct reservation_id" in b)
        for b in bodies
    )
    property_date_trap = any(
        "property_date" in b and "stay_date" in b and ("not" in b or "instead" in b)
        for b in bodies
    )
    assert rows_vs_reservations or property_date_trap, (
        "no skill explicitly cautions rows-vs-reservations or property_date misuse"
    )


# Scenario 7 — OTA / block concentration judgment (bonus)
def test_concentration_skill_references_share():
    blob = " ".join(p.read_text(encoding="utf-8") for p in _skill_files())
    assert "share_of_revenue" in blob
    assert "block_share_of_revenue" in blob
