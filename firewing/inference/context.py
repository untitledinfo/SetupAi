"""Context budget management with a pluggable trim strategy.

Beta v1 only supported "drop the oldest turns" (still the default —
`context_strategy: drop`). This adds `context_strategy: summarize`,
which collapses dropped turns into a single system-role summary
instead of throwing them away outright, using the model itself to
generate the summary. Summarization costs an extra generation call
when the budget is exceeded, so it's opt-in, not the default.
"""

from __future__ import annotations

from typing import Callable

from firewing.inference.conversation import Conversation, Message, content_to_text

SummarizerFn = Callable[[str], str]


def trim_by_dropping(conversation: Conversation, count_tokens_fn, max_tokens: int) -> None:
    conversation.trim_to_budget(count_tokens_fn, max_tokens)


def trim_by_summarizing(
    conversation: Conversation,
    count_tokens_fn,
    max_tokens: int,
    summarizer_fn: SummarizerFn,
    keep_recent_turns: int = 4,
) -> None:
    """Summarize everything except the most recent `keep_recent_turns`
    messages into a single system note, if the conversation is over
    budget. Recent turns are always kept verbatim — summarization only
    touches history the model has already "moved past".
    """
    rendered = "\n".join(content_to_text(m.content) for m in conversation.messages)
    system_len = count_tokens_fn(conversation.system_prompt) if conversation.system_prompt else 0
    if count_tokens_fn(rendered) + system_len <= max_tokens:
        return

    if len(conversation.messages) <= keep_recent_turns:
        # Nothing safe to summarize without touching "recent" turns —
        # fall back to dropping so we don't violate keep_recent_turns.
        trim_by_dropping(conversation, count_tokens_fn, max_tokens)
        return

    to_summarize = conversation.messages[:-keep_recent_turns]
    recent = conversation.messages[-keep_recent_turns:]

    transcript = "\n".join(f"{m.role}: {content_to_text(m.content)}" for m in to_summarize)
    summary_prompt = (
        "Summarize the key facts, decisions, and context from this earlier "
        "part of a conversation in a few sentences, for use as background "
        "context in continuing it:\n\n" + transcript
    )
    summary_text = summarizer_fn(summary_prompt)

    summary_note = f"[Earlier conversation summary]: {summary_text}"
    if conversation.system_prompt:
        conversation.system_prompt = f"{conversation.system_prompt}\n\n{summary_note}"
    else:
        conversation.system_prompt = summary_note

    conversation.messages = recent

    # If it's still over budget even after summarizing (e.g. a huge
    # single recent message), fall back to dropping from what's left.
    trim_by_dropping(conversation, count_tokens_fn, max_tokens)
