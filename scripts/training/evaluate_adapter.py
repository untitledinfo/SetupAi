"""Side-by-side comparison of the base model vs. a trained LoRA adapter
on a held-out prompt set. This is a sanity check, not a rigorous eval
suite — it prints both outputs so a human can judge whether the
fine-tune actually helped, rather than assuming it did.

Usage:
    python scripts/training/evaluate_adapter.py \
        --model-path Qwen/Qwen3-Omni-30B-A3B-Instruct \
        --adapter-path ./firewing-lora-adapter \
        --prompts data/eval_prompts.txt
"""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-path", default="Qwen/Qwen3-Omni-30B-A3B-Instruct")
    parser.add_argument("--adapter-path", required=True)
    parser.add_argument("--prompts", required=True, type=Path, help="One prompt per line")
    parser.add_argument("--max-new-tokens", type=int, default=256)
    args = parser.parse_args()

    if not args.prompts.exists():
        raise SystemExit(f"Prompts file not found: {args.prompts}")

    prompts = [p.strip() for p in args.prompts.read_text(encoding="utf-8").splitlines() if p.strip()]
    if not prompts:
        raise SystemExit("Prompts file is empty")

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel

    tokenizer = AutoTokenizer.from_pretrained(args.model_path, trust_remote_code=True)
    base_model = AutoModelForCausalLM.from_pretrained(
        args.model_path, torch_dtype=torch.bfloat16, trust_remote_code=True
    )
    tuned_model = PeftModel.from_pretrained(base_model, args.adapter_path)

    def generate(model, prompt: str) -> str:
        rendered = tokenizer.apply_chat_template(
            [{"role": "user", "content": prompt}], tokenize=False, add_generation_prompt=True
        )
        inputs = tokenizer(rendered, return_tensors="pt")
        output = model.generate(**inputs, max_new_tokens=args.max_new_tokens, do_sample=False)
        return tokenizer.decode(output[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)

    for i, prompt in enumerate(prompts, 1):
        print(f"\n=== Prompt {i} ===\n{prompt}\n")
        print(f"--- Base model ---\n{generate(base_model, prompt)}\n")
        print(f"--- Fine-tuned ---\n{generate(tuned_model, prompt)}\n")


if __name__ == "__main__":
    main()
