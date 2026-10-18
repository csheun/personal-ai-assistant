from tests.contract_scenarios import FIXTURE, record_all, render


async def test_runner_output_matches_shared_contract_fixture() -> None:
    """If this fails after an intentional change, regenerate with `python -m tests.contract_scenarios --write`
    and make sure the frontend contract test still passes."""
    assert render(await record_all()) == FIXTURE.read_text()
