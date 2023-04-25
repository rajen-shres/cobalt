import re
import shlex

from tests.simple_selenium import SimpleSelenium

command_lookup = {
    "enter": 'manager.enter_value_into_field_by_name("WORDS_3", "WORDS_1")',
    "enter_parameter": 'manager.enter_value_into_field_by_name("WORDS_3", WORDS_1)',
    "click": 'manager.press_by_text("WORDS_1")',
    "click_by_name": 'manager.press_by_name("WORDS_1")',
    "find": 'manager.find_by_text("WORDS_1")',
    "title": 'manager.set_title("WORDS_1")',
    "go": 'manager.go_to("WORDS_1")',
    "screenshot": 'manager.screenshot("WORDS_1")',
    "send_enter": 'manager.send_enter("WORDS_2")',
    "log": 'manager.add_message("WORDS_1", bold=True)',
    "selectpicker": 'manager.selectpicker("WORDS_2", "WORDS_4")',
    "dropdown": 'manager.dropdown("WORDS_2", "WORDS_4")',
    "sleep": "manager.sleep(WORDS_1)",
}


def simple_selenium_parser(script_file, base_url, password, browser, show, silent):
    """translates a test script into code and runs it"""

    with open(f"tests/scripts/{script_file}") as in_file:
        script = in_file.readlines()

    commands = build_commands(script)
    run_commands(commands, base_url, password, browser, show, silent)


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

        commands.append(f"manager.current_action='{line}'")

        cmd_string = build_command_line(words)

        if cmd_string:
            commands.append(cmd_string)

    return commands


def build_command_line(words):
    """process a single command line"""

    # the first word is the keyword
    key_word = words[0].lower()

    # Find a match or None from command_lookup
    cmd_string = command_lookup.get(key_word)

    # Go through and replace the placeholders with the words from the command
    for index, word in enumerate(words[1:]):
        cmd_string = cmd_string.replace(f"WORDS_{index + 1}", word)

    return cmd_string


def run_commands(commands, base_url, password, browser, show, silent):
    """execute the commands"""

    manager = SimpleSelenium(
        base_url=base_url, browser=browser, show=show, silent=silent
    )

    for cmd_string in commands:
        exec(cmd_string)

    manager.handle_finish()
