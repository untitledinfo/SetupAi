"""LoRA fine-tuning for the FIREWING base model (Qwen3-Omni).

This trains a LoRA adapter on top of the frozen base weights — not a
full fine-tune. That's a deliberate default: LoRA needs far less VRAM,
produces a small (~tens to hundreds of MB) adapter file instead of a
new full copy of a 30B model, and is easy to swap/version. Full
fine-tuning is possible by setting `--full-finetune`, but expect to
need multi-GPU/80GB-class hardware for that on this base model size —
validate on your own hardware before committing to it.

This script does NOT run automatically as part of anything else in
this repo. It's meant to be run explicitly, on your own GPU machine,
against data you've prepared and validated with prepare_dataset.py.

Usage:
    python scripts/training/train_lora.py \
        --dataset data/tokenized \
        --model-path Qwen/Qwen3-Omni-30B-A3B-Instruct \
        --output-dir ./firewing-lora-adapter \
        --config scripts/training/training_config.yaml
"""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml


def load_training_config(path: str | None) -> dict:
    defaults = {
        "lora_r": 16,
        "lora_alpha": 32,
        "lora_dropout": 0.05,
        "target_modules": ["q_proj", "k_proj", "v_proj", "o_proj"],
        "learning_rate": 2e-4,
        "num_train_epochs": 3,
        "per_device_train_batch_size": 1,
        "gradient_accumulation_steps": 16,
        "warmup_ratio": 0.03,
        "logging_steps": 10,
        "save_steps": 200,
        "bf16": True,
    }
    if path and Path(path).exists():
        with open(path, "r", encoding="utf-8") as fh:
            overrides = yaml.safe_load(fh) or {}
        defaults.update(overrides)
    return defaults


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, help="Path from prepare_dataset.py --output")
    parser.add_argument("--model-path", default="Qwen/Qwen3-Omni-30B-A3B-Instruct")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--config", default="scripts/training/training_config.yaml")
    parser.add_argument("--full-finetune", action="store_true", help="Train all weights instead of a LoRA adapter (needs far more VRAM)")
    parser.add_argument("--resume-from-checkpoint", default=None)
    args = parser.parse_args()

    cfg = load_training_config(args.config)

    # Imports are deliberately inside main() so `--help` and argument
    # validation work even without torch/transformers/peft installed.
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments, Trainer
    from datasets import load_from_disk

    print(f"Loading base model: {args.model_path}")
    tokenizer = AutoTokenizer.from_pretrained(args.model_path, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        args.model_path,
        torch_dtype=torch.bfloat16 if cfg["bf16"] else torch.float32,
        trust_remote_code=True,
    )

    if not args.full_finetune:
        from peft import LoraConfig, get_peft_model

        lora_config = LoraConfig(
            r=cfg["lora_r"],
            lora_alpha=cfg["lora_alpha"],
            lora_dropout=cfg["lora_dropout"],
            target_modules=cfg["target_modules"],
            task_type="CAUSAL_LM",
        )
        model = get_peft_model(model, lora_config)
        model.print_trainable_parameters()
    else:
        print(
            "WARNING: --full-finetune trains every parameter. This needs "
            "substantially more VRAM than LoRA. Make sure you've validated "
            "this fits your hardware (see docs/training.md) before proceeding."
        )

    print(f"Loading tokenized dataset from {args.dataset}")
    dataset = load_from_disk(args.dataset)

    training_args = TrainingArguments(
        output_dir=args.output_dir,
        per_device_train_batch_size=cfg["per_device_train_batch_size"],
        gradient_accumulation_steps=cfg["gradient_accumulation_steps"],
        num_train_epochs=cfg["num_train_epochs"],
        learning_rate=cfg["learning_rate"],
        warmup_ratio=cfg["warmup_ratio"],
        logging_steps=cfg["logging_steps"],
        save_steps=cfg["save_steps"],
        bf16=cfg["bf16"],
        report_to=[],  # no external experiment tracker wired up by default
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=dataset,
        tokenizer=tokenizer,
    )

    trainer.train(resume_from_checkpoint=args.resume_from_checkpoint)

    print(f"Saving final adapter/model to {args.output_dir}")
    trainer.save_model(args.output_dir)
    tokenizer.save_pretrained(args.output_dir)

    print("Done. To use this adapter with FIREWING, see docs/training.md")
    print("('Using a trained adapter' section) — set model.model_path to")
    print("the base model and add the adapter path to your config.")


if __name__ == "__main__":
    main()
