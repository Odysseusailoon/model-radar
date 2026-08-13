"""Shared helpers for talking to the Anthropic-compatible gateway.

The gateway in front of us returns an extended-thinking block ahead of the
answer on every request, so `msg.content[0]` is a `thinking` block whose
`.text` is None. Any caller that indexes content[0] blindly raises
AttributeError. Route replies through `first_text` instead.

Thinking also spends 1.5-4k of the `max_tokens` budget before the answer
starts, so calls sized for the answer alone now come back truncated with
stop_reason == "max_tokens". Budget accordingly.
"""
from __future__ import annotations


def first_text(msg) -> str:
    """Return the first non-empty text block of a reply.

    Raises ValueError if the reply carried no text at all -- that is a real
    failure worth surfacing, not something to paper over with an empty string.
    """
    for block in msg.content:
        if getattr(block, "type", None) == "text" and getattr(block, "text", None):
            return block.text
    raise ValueError(
        f"reply had no text block (stop_reason={getattr(msg, 'stop_reason', '?')}, "
        f"blocks={[getattr(b, 'type', '?') for b in msg.content]})"
    )
