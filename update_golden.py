import yaml
from copy import deepcopy
from pluma.tools.registry import get_default_tool_registry

registry = get_default_tool_registry()

# Define dummy args for each tool type
TOOL_DUMMY_ARGS = {
    'mute': {},
    'unmute': {},
    'set_volume': {'level': 50},
    'get_volume_status': {},
    'open_app': {'app_name': 'notepad'},
    'close_app': {'app_name': 'notepad'},
    'focus_app': {'app_name': 'notepad'},
    'list_apps': {},
    'inspect_active_window': {},
    'list_windows': {},
    'focus_window': {'hwnd': 1234},
    'minimize_window': {'hwnd': 1234},
    'maximize_window': {'hwnd': 1234},
    'restore_window': {'hwnd': 1234},
    'click_element': {'snapshot_id': 'snap-1', 'target_ref': 'snap-1::btn1'},
    'type_into_element': {'snapshot_id': 'snap-1', 'target_ref': 'snap-1::txt1', 'text': 'hello'},
    'list_files': {'path': '.'},
    'find_file': {'pattern': 'config.txt'},
    'create_folder': {'path': 'new_folder'},
    'move_file': {'source': 'a.txt', 'destination': 'b.txt'},
    'rename_file': {'path': 'a.txt', 'new_name': 'b.txt'},
    'get_clipboard_text': {},
    'clipboard_clear': {},
    'get_system_status': {},
    'battery_status': {},
    'show_activity': {},
    'undo_last': {},
    'stop_current': {}
}

with open('tests/fixtures/golden_commands.yaml', 'r', encoding='utf-8') as f:
    data = yaml.safe_load(f)

new_commands = []
for cmd in data.get('commands', []):
    tools = cmd.get('expected_tools', [])
    if tools:
        t = tools[0]
        args = TOOL_DUMMY_ARGS.get(t, {})
        # try to validate just to make sure it's valid for the tool
        try:
            norm_args = registry.validate_call(t, args)
        except Exception:
            norm_args = args # fallback
    else:
        norm_args = {}
        
    cmd['normalized_args'] = norm_args
    cmd['expected_policy_decision'] = 'ALLOW'
    cmd['expected_execution_status'] = 'SUCCEEDED'
    cmd['expected_postcondition_present'] = True
    new_commands.append(cmd)

data['commands'] = new_commands

with open('tests/fixtures/golden_commands.yaml', 'w', encoding='utf-8') as f:
    yaml.dump(data, f, default_flow_style=False, sort_keys=False)

print('Golden commands updated!')
