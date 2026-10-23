"""test_scenarios.py - runs every test scenario in tests/scenarios/ through the engine.

What this file is for:
    Each scenario file (P1.yaml ... P15.yaml) describes one complete project and the
    result the law side expects for it. This test:
      1. reads base_project.yaml (the complete, valid basic project)
      2. reads one scenario file and applies its "answers" on top of the basic project
      3. turns amounts written as text ("100000.00") into Decimal (decision D25)
      4. runs engine.evaluate()
      5. compares the result with the scenario's "expected" part
    pytest shows every scenario as its own test, e.g. "test_scenario[P3] PASSED".
    A new scenario only needs a new YAML file; this Python file does not change.

The "expected" part of a scenario file:
    can_generate            true / false (required)
    clauses                 selected clause IDs in contract order (required)
    errors                  rule IDs of the errors, compared as a set (required)
    warnings                rule IDs of the warnings, compared as a set (required)
    error_fields            optional: {rule ID: [fields]} where the errors are shown
    ignored_fields          optional: answers the engine must ignore (compared as a set)
    contract_text_contains  optional: texts that must appear in the filled clauses

How it fits into the project:
    AI_PROMPT step 13; the scenarios themselves are step 12. Together they are the
    "x of N scenarios correct" test report of the project plan (week 7). Run:
        python -m pytest tests/test_scenarios.py -v

Which documents it implements:
    AI_PROMPT section 9 (P1-P10), law packet Task 11 (REF02, REF03, REF07, REF08,
    REF09 as P11-P15, decision R7), decisions D20 (rule IDs compared as sets),
    D25 (no floats), D38 (scenarios start from the basic project).
"""

from decimal import Decimal  # amounts and percentages become exact Decimal values
from pathlib import Path  # file paths that work on every operating system

import pytest  # the test framework
import yaml  # reads the scenario files

from data_loader import load_knowledge  # the real knowledge base
from engine import evaluate  # the rule engine under test


SCENARIO_DIR = Path(__file__).parent / "scenarios"  # the folder tests/scenarios/
BASE_FILE = SCENARIO_DIR / "base_project.yaml"  # the basic project every scenario starts from


def _scenario_number(path):
    """Sort key: P2 comes before P10 (number order, not alphabetical order)."""
    return int(path.stem[1:])  # "P10" -> 10


SCENARIO_FILES = sorted(SCENARIO_DIR.glob("P*.yaml"), key=_scenario_number)  # P1.yaml, P2.yaml, ..., P15.yaml


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")  # load the YAML knowledge base once for all scenarios
def knowledge():
    """The real knowledge base from data/."""
    return load_knowledge()  # read and check the four YAML files


def read_yaml(path):
    """Read one YAML file and return its content."""
    with path.open(encoding="utf-8") as file:  # UTF-8 for characters like ü
        return yaml.safe_load(file)  # safe_load builds plain data only


def to_engine_types(answers, knowledge):
    """Return a copy of the answers with amounts and percentages turned into Decimal.

    The field types come from parameters.yaml. Answers for unknown fields (such as
    old penalty values) are kept as they are; the engine ignores them anyway.
    Example: {"contract_price": "100000.00"} -> {"contract_price": Decimal("100000.00")}
    """
    converted = {}  # the result, filled below
    for field_id, value in answers.items():  # each answer
        field = knowledge["fields"].get(field_id)  # its definition, or None if unknown
        converted[field_id] = convert_value(value, field, field_id) if field else value  # convert known fields only
    return converted  # the answers in the types the engine expects


def convert_value(value, definition, where):
    """Convert one answer to the type of its field or column (Decimal for money and percentages).

    Raises ValueError for a float, because amounts must be written in quotes in the
    scenario files (decision D25).
    """
    if value is None:  # not answered
        return None  # stays None
    if isinstance(value, float):  # YAML made a float because the quotes are missing
        raise ValueError(f"{where}: write amounts in quotes, e.g. \"100000.00\" (decision D25)")  # explain the fix
    if definition["type"] in ("decimal_chf", "decimal_percent"):  # money or percentage
        return Decimal(str(value))  # "100000.00" -> Decimal("100000.00"); str() also accepts whole numbers
    if definition["type"] == "list":  # a table such as milestones
        columns = {column["id"]: column for column in definition["columns"]}  # column ID -> definition
        rows = []  # the converted rows
        for row in value:  # each row of the table
            new_row = {}  # the converted cells of this row
            for key, cell in row.items():  # each cell
                new_row[key] = convert_value(cell, columns[key], f"{where}.{key}") if key in columns else cell  # convert
            rows.append(new_row)  # keep the converted row
        return rows  # the converted table
    return value  # dates, text, enums, true/false and whole numbers are already right


def rule_ids(entries):
    """The set of rule IDs in a list of errors or warnings (W_PRICE twice counts once, D20)."""
    return {entry["rule_id"] for entry in entries}  # a set ignores order and duplicates


# ---------------------------------------------------------------------------
# The test: one run per scenario file
# ---------------------------------------------------------------------------

def test_there_are_scenarios():
    """The folder really contains scenario files (otherwise the test below would silently run 0 times)."""
    assert len(SCENARIO_FILES) >= 10  # at least P1-P10 from AI_PROMPT section 9


@pytest.mark.parametrize("path", SCENARIO_FILES, ids=[path.stem for path in SCENARIO_FILES])  # one test per file
def test_scenario(path, knowledge):
    """Run one scenario through the engine and compare the result with its "expected" part."""
    scenario = read_yaml(path)  # the scenario file
    assert scenario["id"] == path.stem  # the ID inside the file matches the file name
    answers = {**read_yaml(BASE_FILE)["answers"], **(scenario.get("answers") or {})}  # basic project + changes
    result = evaluate(to_engine_types(answers, knowledge), knowledge)  # run the engine
    expected = scenario["expected"]  # what the law side expects

    # the four required comparisons
    assert result["can_generate"] == expected["can_generate"], "can_generate"  # "Generate" allowed or not
    assert [r["clause_id"] for r in result["selected_clauses"]] == expected["clauses"], "selected clauses"  # clauses
    assert rule_ids(result["errors"]) == set(expected["errors"]), "errors"  # errors (as a set)
    assert rule_ids(result["warnings"]) == set(expected["warnings"]), "warnings"  # warnings (as a set)

    # the optional comparisons
    for rule_id, fields in (expected.get("error_fields") or {}).items():  # where the errors are shown
        shown_at = {e["field"] for e in result["errors"] if e["rule_id"] == rule_id}  # fields of this rule
        assert shown_at == set(fields), f"fields of {rule_id}"  # compare as a set
    if "ignored_fields" in expected:  # answers the engine must ignore
        assert set(result["ignored_fields"]) == set(expected["ignored_fields"]), "ignored fields"  # compare
    contract_text = "\n".join(record["text"] for record in result["selected_clauses"])  # all filled clause texts
    for snippet in expected.get("contract_text_contains") or []:  # each text that must appear
        assert snippet in contract_text, f"contract text should contain: {snippet}"  # it is there
