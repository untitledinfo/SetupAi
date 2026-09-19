# Fine-Tuning FIREWING

This covers training a LoRA adapter (or, optionally, full fine-tune)
on top of the Qwen3-Omni base model. **This is not something the
FIREWING API/CLI does automatically** — it's a separate offline
workflow you run yourself, on your own GPU hardware.

## Hardware reality check

Qwen3-Omni-30B-A3B is a 30B-total/3B-active MoE model. LoRA fine-tuning
still needs to hold the full base model in memory (frozen) plus
gradients for the (small) LoRA parameters and optimizer state. Realistic
minimum: a single GPU with 48GB+ VRAM, more comfortably 80GB
(A100/H100-class). Full fine-tuning (`--full-finetune`) needs
substantially more — multi-GPU is the realistic path there. These are
architectural expectations, not measured numbers; confirm actual VRAM
usage on your hardware before committing to a long run — it will fail
fast (OOM) rather than silently if you're short.

## Workflow

### 1. Prepare your data

One JSONL file, one conversation per line:

```json
{"messages": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]}
```

Where does this data come from? **Not included here** — you need to
supply real conversations relevant to what you want FIREWING to get
better at. Do not train on data you don't have the rights to use, and
don't fabricate a dataset description in the model card later — see
`docs/model-card.md`.

```bash
pip install -r requirements.txt -r requirements-training.txt

python scripts/training/prepare_dataset.py \
  --input data/raw_conversations.jsonl \
  --output data/tokenized \
  --model-path Qwen/Qwen3-Omni-30B-A3B-Instruct \
  --max-length 4096
```

This validates your data (every conversation must end with an
assistant turn, no empty messages, valid roles) and fails loudly on
anything malformed rather than training on garbage silently.

### 2. Train

```bash
python scripts/training/train_lora.py \
  --dataset data/tokenized \
  --model-path Qwen/Qwen3-Omni-30B-A3B-Instruct \
  --output-dir ./firewing-lora-adapter \
  --config scripts/training/training_config.yaml
```

Adjust `scripts/training/training_config.yaml` for your run — the
shipped values are reasonable defaults, not values tuned for your
specific data. Watch the training loss; if it's not decreasing, stop
and check your data/learning rate before spending more GPU hours.

### 3. Evaluate before deploying

```bash
python scripts/training/evaluate_adapter.py \
  --model-path Qwen/Qwen3-Omni-30B-A3B-Instruct \
  --adapter-path ./firewing-lora-adapter \
  --prompts data/eval_prompts.txt
```

This prints base-vs-fine-tuned outputs side by side so you can
actually judge whether it helped. There's no automated pass/fail here
— that requires eval criteria specific to what you were trying to
improve.

### 4. Using a trained adapter in FIREWING

Two options:

**a) Keep it as a separate adapter (recommended — smaller, reversible):**
Extend `firewing/model/loader.py` to optionally load a PEFT adapter on
top of the base model (add an `adapter_path` field to `ModelConfig` and
call `PeftModel.from_pretrained(model, adapter_path)` after loading the
base). This isn't wired up by default in this beta — it's a small,
deliberate addition so you opt into it once you actually have a
trained adapter to load.

**b) Merge the adapter into the base weights:**
```python
merged = tuned_model.merge_and_unload()
merged.save_pretrained("./firewing-merged")
```
Then point `model.model_path` at the merged directory. Larger on disk,
but no runtime dependency on `peft`.

## Updating the model card

If you train and deploy a fine-tuned version, update
`docs/model-card.md`'s "Training / fine-tuning information" and
"Evaluation" sections with what you actually did — dataset
description/size/license, training config used, and real before/after
comparisons from `evaluate_adapter.py`. Don't leave the placeholder
text in place once you've actually trained something.
