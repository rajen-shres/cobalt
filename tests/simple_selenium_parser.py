import re
import shlex

from tests.simple_selenium import SimpleSelenium


def simple_selenium_parser(script_file, base_url, password, browser, show):
    """translates a test script into code and runs it"""

    with open(f"tests/scripts/{script_file}") as in_file:
        script = in_file.readlines()

    commands = build_commands(script)
    run_commands(commands, base_url, password, browser, show)


def build_commands(script):
    """does the string manipulation"""
    commands = []
    for line in script:
        line = line.strip()
        # Handle comments
        comment = re.search("#", line)
        if comment:
            line = line[: comment.start()]

        # Use shlex to split 'hello "I am a string" goodbye' into ['hello', 'I am a string', 'goodbye']
        words = shlex.split(line)
        key_word = words[0].lower()
        cmd_string = None

        commands.append(f"manager.current_action='{line}'")

        if key_word == "enter":
            cmd_string = (
                f'manager.enter_value_into_field_by_name("{words[3]}", "{words[1]}")'
            )

        if key_word == "enter_parameter":
            cmd_string = (
                f'manager.enter_value_into_field_by_name("{words[3]}", {words[1]})'
            )

        elif key_word == "click":
            cmd_string = f'manager.press_by_text("{words[1]}")'

        elif key_word == "find":
            cmd_string = f'manager.find_by_text("{words[1]}")'

        elif key_word == "go":
            cmd_string = f'manager.go_to("{words[1]}")'

        elif key_word == "screenshot":
            cmd_string = f'manager.screenshot("{words[1]}")'

        elif key_word == "send_enter":
            cmd_string = f'manager.send_enter("{words[2]}")'

        if cmd_string:
            commands.append(cmd_string)

    return commands


def run_commands(commands, base_url, password, browser, show):
    """execute the commands"""

    manager = SimpleSelenium(base_url=base_url, browser=browser, show=show)

    for cmd_string in commands:
        exec(cmd_string)

    manager.handle_finish()
