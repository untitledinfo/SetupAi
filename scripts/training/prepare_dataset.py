"""Convert raw conversation data into the tokenized training format.

Input format: a JSONL file where each line is one conversation:
    {"messages": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]}

Output: a Hugging Face `datasets` Arrow dataset on disk, ready for
train_lora.py. Kept as a separate step (rather than tokenizing inline
during training) so you can inspect/validate the tokenized data before
spending GPU hours on it.

Usage:
    python scripts/training/prepare_dataset.py \
        --input data/raw_conversations.jsonl \
        --output data/tokenized \
        --model-path Qwen/Qwen3-Omni-30B-A3B-Instruct \
        --max-length 4096
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_conversations(path: Path) -> list[dict]:
    conversations = []
    with open(path, "r", encoding="utf-8") as fh:
        for line_num, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on line {line_num} of {path}: {exc}") from exc
            if "messages" not in record:
                raise ValueError(f"Line {line_num} of {path} missing 'messages' key")
            conversations.append(record)
    return conversations


def validate_conversations(conversations: list[dict]) -> None:
    """Fail loudly on malformed data rather than silently training on garbage."""
    valid_roles = {"system", "user", "assistant"}
    for i, conv in enumerate(conversations):
        messages = conv["messages"]
        if not messages:
            raise ValueError(f"Conversation {i} has no messages")
        for m in messages:
            if m.get("role") not in valid_roles:
                raise ValueError(f"Conversation {i} has invalid role: {m.get('role')}")
            if not m.get("content", "").strip():
                raise ValueError(f"Conversation {i} has an empty message")
        if messages[-1]["role"] != "assistant":
            raise ValueError(
                f"Conversation {i} must end with an assistant message "
                "(that's what the model learns to produce)"
            )


def tokenize_and_save(
    conversations: list[dict],
    model_path: str,
    output_dir: Path,
    max_length: int,
) -> None:
    from transformers import AutoTokenizer
    from datasets import Dataset

    tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    def _render(conv: dict) -> str:
        return tokenizer.apply_chat_template(
            conv["messages"], tokenize=False, add_generation_prompt=False
        )

    def _tokenize(batch: dict) -> dict:
        texts = [_render({"messages": m}) for m in batch["messages"]]
        encoded = tokenizer(
            texts,
            truncation=True,
            max_length=max_length,
            padding="max_length",
        )
        encoded["labels"] = [ids.copy() for ids in encoded["input_ids"]]
        return encoded

    dataset = Dataset.from_list(conversations)
    tokenized = dataset.map(_tokenize, batched=True, remove_columns=dataset.column_names)

    output_dir.mkdir(parents=True, exist_ok=True)
    tokenized.save_to_disk(str(output_dir))

    print(f"Saved {len(tokenized)} tokenized examples to {output_dir}")
    print(f"Example token count (first row): {len(tokenized[0]['input_ids'])}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Path to JSONL conversation file")
    parser.add_argument("--output", required=True, type=Path, help="Directory to write tokenized dataset")
    parser.add_argument("--model-path", default="Qwen/Qwen3-Omni-30B-A3B-Instruct")
    parser.add_argument("--max-length", type=int, default=4096)
    args = parser.parse_args()

    if not args.input.exists():
        raise SystemExit(f"Input file not found: {args.input}")

    conversations = load_conversations(args.input)
    validate_conversations(conversations)
    print(f"Loaded and validated {len(conversations)} conversations from {args.input}")

    tokenize_and_save(conversations, args.model_path, args.output, args.max_length)


if __name__ == "__main__":
    main()
