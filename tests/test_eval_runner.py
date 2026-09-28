import yaml
from pathlib import Path
from app.config import settings
from app.llm.mock_client import MockLLMClient
from app.agent.orchestrator import AgentOrchestrator
from app.services.db import init_db

def test_run_evaluation_suite(tmp_path):
    # Setup test DB
    settings.database_path = tmp_path / "eval_test.db"
    settings.trace_log_path = tmp_path / "eval_traces.jsonl"
    init_db()

    eval_file = Path(__file__).parent / "eval_cases.yaml"
    assert eval_file.exists(), "eval_cases.yaml must exist"

    with open(eval_file, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    eval_cases = data.get("eval_cases", [])
    assert len(eval_cases) > 0, "No evaluation cases found"

    mock_client = MockLLMClient()
    orchestrator = AgentOrchestrator(llm_client=mock_client)

    passed_count = 0
    total_count = len(eval_cases)

    for case in eval_cases:
        case_id = case["id"]
        customer_id = case.get("customer_id", "CUST-001")
        prompt = case["prompt"]

        response = orchestrator.process_chat(
            message=prompt,
            customer_id=customer_id
        )

        # Check expected tools
        expected_tools = case.get("expected_tools", [])
        actual_tools = [tc.tool_name for tc in response.tool_calls]
        for expected_tool in expected_tools:
            assert expected_tool in actual_tools, (
                f"Case '{case_id}': Expected tool '{expected_tool}' was not called. Actual: {actual_tools}"
            )

        # Check expected status in reply
        if "expected_status_in_reply" in case:
            expected_status = case["expected_status_in_reply"].lower()
            assert expected_status in response.reply.lower(), (
                f"Case '{case_id}': Expected status '{expected_status}' not in reply: {response.reply}"
            )

        # Check expected keywords in reply
        if "expected_keywords_in_reply" in case:
            for kw in case["expected_keywords_in_reply"]:
                assert kw.lower() in response.reply.lower(), (
                    f"Case '{case_id}': Expected keyword '{kw}' not found in reply: {response.reply}"
                )

        # Check refusal
        if case.get("expected_refusal", False):
            assert "cannot fulfill this request" in response.reply.lower()

        passed_count += 1

    assert passed_count == total_count, f"Evaluation suite passed {passed_count}/{total_count}"
