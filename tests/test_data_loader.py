"""test_data_loader.py - automatic tests for data_loader.py.

What this file is for:
    It proves two things:
    1. The real data files in data/ load without mistakes, and the result has
       the expected form (dictionaries by ID, Decimal for money, real dates).
    2. Typical mistakes in the YAML files are caught with a clear message.
       For this, each test copies the data folder into a temporary folder,
       puts ONE mistake into the copy, and checks the error message.
       The real files in data/ are never changed.

How it fits into the project:
    AI_PROMPT step 7 ("Tests for step 6"). Run with pytest from the project root:
        python -m pytest tests/test_data_loader.py -v

Which documents it implements:
    AI_PROMPT step 6 checks (unique IDs, one SEL_ rule per clause, placeholders,
    citations, clear errors), handoff App. C (metadata), decision D6 (conditions).

Note: the mistakes are put in by replacing an exact piece of text in a copied
YAML file. If a YAML file changes later, the helper break_file() fails with a clear
message saying which text it could not find; then the test needs the new text.
"""

import shutil  # copies the whole data folder into a temporary folder
from datetime import date  # to compare with dates read from YAML
from decimal import Decimal  # to compare with money values converted by the loader

import pytest  # the test framework: provides tmp_path and pytest.raises

from data_loader import DEFAULT_DATA_DIR, DataError, load_knowledge  # the module under test


# ---------------------------------------------------------------------------
# Helpers used by the tests
# ---------------------------------------------------------------------------

@pytest.fixture  # pytest creates this value for every test that asks for "data_copy"
def data_copy(tmp_path):
    """Copy the real data folder into a new temporary folder and return its path.

    tmp_path is a fresh, empty folder that pytest creates for each test and
    deletes later, so every test starts from clean, correct data.
    """
    folder = tmp_path / "data"  # where the copy goes
    shutil.copytree(DEFAULT_DATA_DIR, folder)  # copy sources.yaml, parameters.yaml, clauses.yaml, rules.yaml
    return folder  # the test changes files in this copy only


def break_file(folder, file_name, old_text, new_text):
    """Replace old_text with new_text in one copied YAML file, to put in a mistake.

    Fails the test at once if old_text is not found, so a changed YAML file is
    noticed immediately instead of silently testing nothing.
    """
    path = folder / file_name  # the copied file
    content = path.read_text(encoding="utf-8")  # its text
    assert old_text in content, f"test setup: text not found in {file_name}: {old_text!r}"  # guard (see docstring)
    path.write_text(content.replace(old_text, new_text, 1), encoding="utf-8")  # replace the first match and save


def error_message(folder):
    """Load the data in folder, expect a DataError, and return its message."""
    with pytest.raises(DataError) as caught:  # the test fails if NO DataError is raised
        load_knowledge(folder)  # load the (broken) copy
    return str(caught.value)  # the text with the list of mistakes


# ---------------------------------------------------------------------------
# 1. The real data loads correctly
# ---------------------------------------------------------------------------

def test_real_data_loads_without_mistakes():
    """The four files in data/ load and contain the main parts of topic 1."""
    knowledge = load_knowledge()  # read and check the real data folder
    assert knowledge["law_version"] == "2026-10-01"  # decision D12
    assert {"PRICE_FIXED", "PRICE_ESTIMATE", "PAYMENT_ON_COMPLETION", "PAYMENT_MILESTONE"} <= set(knowledge["clauses"])  # 4 clauses
    assert {"R_SCOPE", "R_REQUIRED", "R_PRICE", "R_PAY", "W_PRICE", "W_CONSUMER", "R_CROSS"} <= set(knowledge["rules"])  # rules
    assert {"price_clause", "payment_clause"} <= set(knowledge["slots"])  # the two slots of skeleton section 5


def test_entries_are_found_by_id_in_file_order():
    """Every part is a dictionary {ID: entry}, in the same order as the YAML file."""
    knowledge = load_knowledge()  # real data
    assert knowledge["rules"]["R_PRICE"]["id"] == "R_PRICE"  # look-up by ID works
    assert list(knowledge["fields"])[0] == "contract_date"  # the first question in parameters.yaml stays first
    assert list(knowledge["fields"])[-1] == "contractor_signatory_capacity"  # and the last stays last


def test_condition_values_get_the_right_python_type():
    """Money values in conditions become Decimal (never float), dates stay dates."""
    knowledge = load_knowledge()  # real data
    price_case = knowledge["rules"]["R_PRICE"]["cases"][0]["when"]  # {field: contract_price, op: at_most, value: 0}
    assert price_case["value"] == Decimal("0") and isinstance(price_case["value"], Decimal)  # converted to Decimal
    scope_case = knowledge["rules"]["R_SCOPE"]["cases"][0]["when"]  # {field: contract_date, op: less_than, ...}
    assert scope_case["value"] == date(2026, 1, 1)  # read as a real date


# ---------------------------------------------------------------------------
# 2. Problems with whole files
# ---------------------------------------------------------------------------

def test_missing_file_is_reported(data_copy):
    """A missing YAML file stops loading with 'file not found'."""
    (data_copy / "rules.yaml").unlink()  # delete rules.yaml from the copy
    assert "rules.yaml: file not found" in error_message(data_copy)  # clear message


def test_yaml_syntax_error_is_reported(data_copy):
    """A file that is not valid YAML stops loading with 'YAML syntax error'."""
    (data_copy / "rules.yaml").write_text("rules: [this list is never closed\n", encoding="utf-8")  # broken YAML
    assert "rules.yaml: YAML syntax error" in error_message(data_copy)  # clear message


# ---------------------------------------------------------------------------
# 3. One mistake per test (AI_PROMPT step 6 checks)
# ---------------------------------------------------------------------------

def test_duplicate_id_is_reported(data_copy):
    """The same ID used twice in one list is reported."""
    break_file(data_copy, "sources.yaml", "- id: CO_375_1_TO_2", "- id: CO_375")  # CO_375 now exists twice
    assert "ID 'CO_375' is used twice" in error_message(data_copy)  # clear message


def test_unknown_field_in_condition_is_reported(data_copy):
    """A typo in a field name inside a rule condition is reported with its location."""
    break_file(data_copy, "rules.yaml", "{field: estimate_basis, op: is_empty}", "{field: estimat_basis, op: is_empty}")  # typo
    message = error_message(data_copy)  # load and get the message
    assert "R_PRICE, case 2" in message and "unknown field 'estimat_basis'" in message  # rule, case and field are named


def test_unknown_enum_answer_in_condition_is_reported(data_copy):
    """A condition comparing an enum with a value that is not an allowed answer is reported."""
    break_file(data_copy, "rules.yaml", "{field: price_type, op: equals, value: fixed}", "{field: price_type, op: equals, value: fixd}")  # typo
    assert "'fixd' is not an allowed answer of price_type" in error_message(data_copy)  # clear message


def test_unknown_operator_is_reported(data_copy):
    """An operator that the engine does not know is reported."""
    break_file(data_copy, "rules.yaml", "op: at_most, value: 0", "op: at_mostt, value: 0")  # typo in the operator
    assert "unknown operator 'at_mostt'" in error_message(data_copy)  # clear message


def test_unknown_citation_is_reported(data_copy):
    """A clause citing an ID that is not in sources.yaml is reported."""
    break_file(data_copy, "clauses.yaml", "citations: [CO_374, CO_375_1_TO_2]", "citations: [CO_374, CO_999]")  # unknown ID
    assert "clause PRICE_ESTIMATE: unknown citation 'CO_999'" in error_message(data_copy)  # clear message


def test_placeholder_missing_from_inputs_is_reported(data_copy):
    """A {placeholder} used in a clause text but not listed in 'inputs' is reported."""
    break_file(data_copy, "clauses.yaml", "inputs: [contract_price, vat_treatment_text]  #", "inputs: [contract_price]  #")  # PRICE_FIXED
    assert "placeholder {vat_treatment_text} is in the text but not in 'inputs'" in error_message(data_copy)  # message


def test_clause_without_sel_rule_is_reported(data_copy):
    """A clause that no SEL_ rule selects is reported (AI_PROMPT step 6)."""
    break_file(data_copy, "rules.yaml", "clause: PAYMENT_MILESTONE ", "clause: PAYMENT_ON_COMPLETION ")  # wrong clause
    message = error_message(data_copy)  # load and get the message
    assert "clause PAYMENT_MILESTONE: needs exactly one SEL_ rule, found 0" in message  # nobody selects it any more
    assert "the ID must be SEL_PAYMENT_ON_COMPLETION" in message  # and the rule ID no longer matches its clause


def test_missing_metadata_flag_is_reported(data_copy):
    """A clause without one of the six safety flags is reported (handoff App. C)."""
    break_file(data_copy, "clauses.yaml", "      statutory_exit_preserved: true          # statutory termination routes stay available\n", "")  # remove flag
    assert "clause PRICE_FIXED: metadata flag 'statutory_exit_preserved' is missing" in error_message(data_copy)  # message


def test_version_written_without_quotes_is_reported(data_copy):
    """A version written as a number (1.1) instead of text ("1.1") is reported."""
    break_file(data_copy, "clauses.yaml", 'version: "1.1"', "version: 1.1")  # PRICE_FIXED, quotes removed
    assert "clause PRICE_FIXED: 'version' must be a non-empty text" in error_message(data_copy)  # clear message


def test_rule_without_message_is_reported(data_copy):
    """An R_ or W_ rule whose case has no message at all is reported."""
    break_file(  # remove the only message of R_CROSS
        data_copy,  # the copied data folder
        "rules.yaml",  # file to change
        '"Internal check failed: a contract section received too many or too few clauses. Please report this problem to the team."',  # old
        "null",  # new: no message
    )  # end of break_file
    assert "R_CROSS, case 1: no message" in error_message(data_copy)  # clear message


# ---------------------------------------------------------------------------
# 4. Several mistakes are reported together
# ---------------------------------------------------------------------------

def test_all_mistakes_are_reported_at_once(data_copy):
    """Two mistakes in two files are both listed in one error message."""
    break_file(data_copy, "rules.yaml", "{field: estimate_basis, op: is_empty}", "{field: estimat_basis, op: is_empty}")  # mistake 1
    break_file(data_copy, "clauses.yaml", "citations: [CO_374, CO_375_1_TO_2]", "citations: [CO_374, CO_999]")  # mistake 2
    message = error_message(data_copy)  # load and get the message
    assert "unknown field 'estimat_basis'" in message  # mistake 1 is listed
    assert "unknown citation 'CO_999'" in message  # mistake 2 is listed too
