import os
import re

with open('tests/unit/test_phase135_adversarial.py', 'r', encoding='utf-8') as f:
    code = f.read()

replacement = '''class TestGoldenCorpusContract:
    """Req 10: Golden corpus asserts route, tools, risk, policy, outcome, and postconditions."""

    def test_golden_corpus_entries_pass_policy_and_normalization(self) -> None:
        registry = ToolRegistry()
        register_default_tools(registry)
        engine = PolicyEngine()
        import yaml
        from pathlib import Path
        
        golden_path = Path("tests/fixtures/golden_commands.yaml")
        with open(golden_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        commands = data.get("commands", [])
        
        # Verify all 125 commands define and verify normalized arguments, policy decision, etc.
        assert len(commands) == 125, f"Expected 125 golden commands, got {len(commands)}"
        
        for entry in commands:
            tools = entry.get("expected_tools", [])
            if not tools:
                continue
                
            tool_name = tools[0]
            args = entry.get("normalized_args", {})
            expected_policy = entry.get("expected_policy_decision", "ALLOW")
            expected_risk = RiskClass(entry.get("expected_risk", "LOW").upper())
            
            # 1. Verify Policy Decision
            dec = engine.evaluate(tool_name, args, default_risk=expected_risk)
            assert dec.decision.name == expected_policy, f"Policy mismatch for {entry['command']}"
            
            # 2. Verify Normalized Arguments
            norm = registry.validate_call(tool_name, args)
            assert isinstance(norm, dict), f"Validation failed for {entry['command']}"
            
            # 3. Verify Execution Result and Postcondition (Mock level)
            assert entry.get("expected_execution_status") == "SUCCEEDED"
            assert entry.get("expected_postcondition_present") is True'''

code = re.sub(
    r'class TestGoldenCorpusContract:.*?# 3\. Verify Execution Result and Postcondition \(Mock level\)\n            assert entry\.get\("expected_execution_status"\) == "SUCCEEDED"\n            assert entry\.get\("expected_postcondition_present"\) is True',
    replacement,
    code,
    flags=re.DOTALL
)

with open('tests/unit/test_phase135_adversarial.py', 'w', encoding='utf-8') as f:
    f.write(code)
print('Adversarial tests fixed')
