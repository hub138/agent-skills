"""测试输出协议三级恢复与风险闸门。"""

from agent_foundation import RecoveryLevel, Rule, RiskLevel, adjudicate, parse_agent_output, scan_paths


def test_output_protocol_three_levels():
    stream = parse_agent_output(['data: {"ok": true}', "noise"])
    assert stream.level is RecoveryLevel.STREAM
    assert stream.payload == {"ok": True}

    embedded = parse_agent_output(["thinking...\n```json\n{\"patch\": []}\n```"])
    assert embedded.level is RecoveryLevel.EMBEDDED
    assert embedded.payload == {"patch": []}

    failed = parse_agent_output(["no json here at all"])
    assert failed.level is RecoveryLevel.FAILED
    assert failed.raw_text == "no json here at all"


def test_risk_gate_scans_rules_and_forbidden_tokens(tmp_path):
    (tmp_path / "src").mkdir()
    target = tmp_path / "src" / "module.py"
    target.write_text("endpoint = 'https://internal.example.com/api'\nplain = 1\n")

    findings = scan_paths(
        tmp_path,
        rules=[Rule(name="internal-endpoint", pattern="internal.example.com", level=RiskLevel.BLOCK)],
        forbidden_substrings=["Forbidden-Token"],
    )
    assert adjudicate(findings) is False
    locations = {finding.location for finding in findings}
    assert any("module.py:1" in location for location in locations)

    (tmp_path / "src" / "module.py").write_text("clean = 1\n")
    clear = scan_paths(tmp_path, rules=[], forbidden_substrings=["forbidden-token"])
    assert clear == []
    assert adjudicate(clear) is True


def test_risk_gate_exempts_gate_definition_itself(tmp_path):
    gate_dir = tmp_path / "tests"
    gate_dir.mkdir()
    gate_file = gate_dir / "test_risk_gate.py"
    gate_file.write_text("BLOCK_WORD = 'BLOCK_WORD'\n")

    findings = scan_paths(
        tmp_path,
        rules=[Rule(name="self-reference", pattern="BLOCK_WORD", level=RiskLevel.BLOCK)],
        exempt_paths=[gate_file],
    )
    assert findings == []
    assert adjudicate(findings) is True
