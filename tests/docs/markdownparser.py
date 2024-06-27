import textwrap
from pathlib import Path


def check_md_file(path: Path) -> None:
    """Parse the contents of a Markdown-file for python code blocks and execute them

    Args:
        path: path to markdown file
    """
    code = _extract_python_code(path.read_text())
    if code == "":
        return

    exec(code, {"__MODULE__": "__main__"})  # noqa: S102


def _check_codeblock_is_python(block: str) -> str:
    lines = block.split("\n")
    if lines[0].replace(" ", "")[3:5] == "py":
        return textwrap.dedent("\n".join(lines[1:]))
    return ""


def _extract_codeblocks(raw_md_content: str) -> list[str]:
    docstring = textwrap.dedent(raw_md_content)
    block = ""
    codeblocks = []

    # Parse the docstring for codeblocks. Assume we start outside a codeblock
    inside_codeblock = False
    lines = docstring.split("\n")
    for i_line in range(len(lines)):
        line = lines[i_line]
        line_beginning = line.strip()

        if line_beginning.startswith("```") and not inside_codeblock:
            inside_codeblock = True
        elif line_beginning.startswith("```") and inside_codeblock:
            codeblocks.append(_check_codeblock_is_python(block))
            block = ""
            inside_codeblock = False

        if inside_codeblock:
            block += line + "\n"

    return [codeblock for codeblock in codeblocks if codeblock != ""]


def _extract_python_code(raw_file_content: str) -> str:
    all_code = ""
    for codeblock in _extract_codeblocks(raw_file_content):
        all_code = f"{all_code}\n{codeblock}"

    return all_code
