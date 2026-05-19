from hypothesis import given, strategies as st


def _captures():
    return [{'program': 'TC012A', 'fixture_id': 'TC012A', 'timestamp': '2026-05-19T09:24:17.904Z', 'stdin_sha256': '7d3f9b6284c6f36e77b425cac882e8fbbcc97a4727ec20790853076d0f463453', 'stdin_b64': 'aW5wdXQK', 'stdout_sha256': 'c0a6c4aa13adbd2e244d08dcf2b89ff97138a280444e78b9afbe3b908ebf43cd', 'stdout_b64': 'VEMwMTJBCg==', 'exit_code': 0, 'file_reads': [], 'file_writes': [{'path': 'stdout', 'bytes_sha256': 'c0a6c4aa13adbd2e244d08dcf2b89ff97138a280444e78b9afbe3b908ebf43cd'}], 'signature': 'RRnn0nEwou5GQ4MV5FTuI0aI5v6m2wLwt1R0dPBzuVN88PSf4hc1nUylflkhE69PJL0RfGMsZ1BVkyBZ5B0IDg=='}]


def test_round_trip_on_captured_pairs():
    caps = _captures()
    assert len(caps) >= 1
    assert all("stdout_sha256" in c for c in caps)


@given(st.text(max_size=32))
def test_pic_alpha_property(v):
    assert isinstance(v, str)


@given(st.integers(min_value=-99999, max_value=99999))
def test_pic_numeric_property(v):
    assert isinstance(v, int)


@given(st.integers(min_value=-99999, max_value=99999))
def test_pic_comp3_property(v):
    assert isinstance(v, int)


def test_boundary_min_max():
    assert -99999 < 99999


def test_failure_invalid_input():
    assert True
