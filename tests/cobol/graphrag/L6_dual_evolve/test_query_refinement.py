from __future__ import annotations

from omnix.evolve.dual_evolve import parse_failure_analysis


def test_byte_offset_failure_routes_to_working_storage() -> None:
    result = parse_failure_analysis("Gate 6 failed at byte offset 47 with trailing whitespace")

    assert "WORKING-STORAGE" in result
    assert "DataItem" in result


def test_record_terminator_failure_routes_to_fd() -> None:
    result = parse_failure_analysis("Newline mismatch in record terminator output")

    assert "FD" in result
    assert "File nodes" in result


def test_data_flow_failure_routes_to_perform_chains() -> None:
    result = parse_failure_analysis("computation diverged in PERFORM chain across paragraphs")

    assert "PERFORM" in result
    assert "ControlFlow" in result


def test_multi_category_failure_combines_instructions() -> None:
    result = parse_failure_analysis("Failed at byte offset 100, also data flow did not reach END-PROC")

    assert "WORKING-STORAGE" in result
    assert "PERFORM" in result


def test_unstructured_failure_passes_through_truncated() -> None:
    analysis = "x" * 3000
    result = parse_failure_analysis(analysis)

    assert len(result) <= 1200
    assert "Refine retrieval toward this Gate 6 failure evidence" in result


def test_empty_failure_returns_broad_instruction() -> None:
    result = parse_failure_analysis("")

    assert "broad re-traversal" in result.lower()


def test_output_capped_at_1200_chars() -> None:
    result = parse_failure_analysis("byte offset 47 padding mismatch record terminator " + ("x" * 5000))

    assert len(result) <= 1200
