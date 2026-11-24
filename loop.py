"""Phase 1: hand-written agentic loop with two tools."""

import json
import sys
import traceback

import anthropic
from dotenv import load_dotenv

from errors import ToolError
from tools.definitions import TOOLS, HANDLERS


# --- Loop configuration -------------------------------------------------------
MODEL = "claude-haiku-5-5"
# Safety net against a runaway loop (and a runaway bill). NOT how the loop
# normally ends: that is end_turn. Hitting this cap means something is wrong (1.1).
MAX_ITERATIONS = 10


def run_tool(block) -> dict:
    """Run one tool_use block and ALWAYS return its tool_result, even on failure.

    A failure becomes data the model can reason about (2.2), instead of crashing
    run() and losing the results that already worked (5.3).
    """
    # Which tool the MODEL chose, with what input: the only way to see tool choice (2.1).
    print(f"[tool] {block.name} {json.dumps(block.input, ensure_ascii=False)}", file=sys.stderr)
    try:
        if block.name not in HANDLERS:
            # The model asked for a tool that doesn't exist: a different input
            # (the right name) would work, so this is validation.
            raise ToolError(
                "validation", False,
                f"Unknown tool {block.name!r}. Available tools: {list(HANDLERS)}.",
                source=block.name,
            )
        output = HANDLERS[block.name](block.input)
        return {
            "type": "tool_result",
            "tool_use_id": block.id,  # links this result to its request
            "content": json.dumps(output),  # content must be a string
        }
    # Most specific first: ToolError IS an Exception, so the order matters.
    except ToolError as err:
        # Classified by the adapter: send it as is.
        error = err.to_dict()
    except Exception:
        # Not classified = a bug in MY code. The traceback is for me (stderr),
        # not for the model: it is noise there and leaks code details.
        traceback.print_exc()
        error = ToolError(
            "permission", False,  # only a human (me) can fix a bug
            "Internal error in the tool, not a problem with your input. "
            "Do not retry. Report it as a coverage gap.",
            source=block.name,
        ).to_dict()
    return {
        "type": "tool_result",
        "tool_use_id": block.id,  # every tool_use still gets its answer
        "is_error": True,
        "content": json.dumps(error),
    }

def run(question: str) -> str:
    """Run the agentic loop until the model ends its turn; return its text answer."""
    load_dotenv()  # puts ANTHROPIC_API_KEY into the environment
    client = anthropic.Anthropic()
    # The whole conversation. The API is stateless, so every call resends all of it
    # and input tokens grow each step.
    messages = [
        {"role": "user", "content": question},
    ]
    for _ in range(MAX_ITERATIONS):
        # 1. Call the model. With tools=..., it may answer OR ask for tools.
        response = client.messages.create(
            model=MODEL,
            max_tokens=2000,  # includes thinking tokens; too low -> stop_reason max_tokens
            tools=TOOLS,
            messages=messages
        )

        # 2. Decide by stop_reason, never by parsing the text (1.1).
        # end_turn = the MODEL decided it has everything and is done -> normal exit.
        if response.stop_reason == "end_turn":
            # content is a list of blocks; keep only text (skip thinking etc.).
            texts = [block.text for block in response.content if block.type == "text"]
            return "".join(texts)

        # Anything other than tool_use (max_tokens, refusal, ...) is not a valid
        # result: fail loudly instead of returning a half answer.
        if response.stop_reason != "tool_use":
            raise RuntimeError(f"Unexpected stop_reason: {response.stop_reason}")

        # 3. stop_reason == tool_use -> the loop CONTINUES.
        # Append the model's turn unchanged (thinking blocks included). Every
        # tool_result must answer a tool_use from the turn right before it.
        messages.append({"role": "assistant", "content": response.content})

        # 4. WE run the tools (the model never runs code). One response can hold
        # several tool_use blocks; answer every one of them.
        results = []
        for block in response.content:
            if block.type == "tool_use":
                results.append(run_tool(block))
        # 5. All results go back in ONE user turn, then loop: the model now sees
        # question -> its tool request -> our results.
        messages.append({"role": "user", "content": results})

    raise RuntimeError(f"No final answer after {MAX_ITERATIONS} steps")


if __name__ == "__main__":
    answer = run("How are my stocks doing?")
    print(answer)
