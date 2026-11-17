import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from masterbrain.endpoints.chat.field_input import turn


def test_question_then_reference_uses_dialogue_and_keeps_typed_slots(monkeypatch):
    completion = AsyncMock()
    monkeypatch.setattr(
        turn,
        "select_client",
        lambda _: SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=completion))
        ),
    )
    data = {
        "model": {"name": "qwen3.5-flash"},
        "protocol": "Sample label and duration in minutes",
        "fields": {"sample": {"type": "string"}, "duration": {"type": "integer"}},
        "filled": [],
        "locale": "en-US",
        "conversation": [],
        "references": [],
        "last_applied": [],
        "current_message": "Explain those fields",
    }

    def output(intent, operations):
        completion.return_value = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=json.dumps(
                            {
                                "intent": intent,
                                "answer": "Explanation",
                                "references": ["sample", "duration"],
                                "operations": operations,
                            }
                        )
                    )
                )
            ]
        )
        return asyncio.run(turn.resolve_recorder_turn(turn.RecorderTurnRequest(**data)))

    assert output("answer", []).operations == []
    data.update(
        conversation=[{"role": "assistant", "content": "Sample label, then duration."}],
        references=["sample", "duration"],
        current_message="Fill those two with 001 and 0",
    )
    result = output(
        "fill",
        [
            {"rf_name": "sample", "rf_value": "001", "source": "001"},
            {"rf_name": "duration", "rf_value": 0, "source": "0"},
        ],
    )
    assert [op.rf_value for op in result.operations] == ["001", 0]
    payload = json.loads(completion.call_args.kwargs["messages"][-1]["content"])
    assert payload["references"] == ["sample", "duration"] and payload["conversation"]
    with pytest.raises(ValueError):
        output("fill", [{"rf_name": "duration", "rf_value": 37, "source": "37"}])
    data["current_message"] = "请把样品编号填写为 LOCAL-041。"
    quoted = {"rf_name": "sample", "rf_value": "LOCAL-041", "source": '"LOCAL-041"'}
    assert output("fill", [quoted]).operations[0].source == "LOCAL-041"
    with pytest.raises(ValueError):
        output("fill", [{**quoted, "source": '"OTHER"'}])
    with pytest.raises(ValueError):
        output("fill", [{**quoted, "rf_name": "unknown"}])
    data["current_message"] = "把 duration 改为 12。"
    number = {"rf_name": "duration", "rf_value": 12, "source": '"12"'}
    assert output("fill", [number]).operations[0].source == "12"
    with pytest.raises(ValueError):
        output("fill", [{**number, "source": '"13"'}])
    data["current_message"] = "把 duration 改为 0。"
    assert (
        output("fill", [{**number, "rf_value": 0, "source": '"0"'}])
        .operations[0]
        .source
        == "0"
    )
    data["current_message"] = '请保留编号中的双引号："LOCAL-041"。'
    assert output("fill", [quoted]).operations[0].source == '"LOCAL-041"'
    literal = {**quoted, "rf_value": '"LOCAL-041"'}
    assert output("fill", [literal]).operations[0].rf_value == '"LOCAL-041"'
    data["current_message"] = "Fill the sample with a label I mentioned earlier."
    with pytest.raises(ValueError):
        output("fill", [quoted])
    with pytest.raises(ValueError):
        output("simulate", [{"rf_name": "sample", "rf_value": "001", "source": "001"}])
