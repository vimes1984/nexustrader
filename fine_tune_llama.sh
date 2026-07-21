#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════
# NexusTrader LLaMA Fine-Tuning Pipeline (CPU Edition)
# ═══════════════════════════════════════════════════════════════════
# Fine-tunes Llama 3.2 3B on trading data using LoRA — NO GPU needed.
# Strategy: Load model in float32, apply LoRA adapters, train on CPU.
# 128GB RAM is sufficient for 3B params at full precision.
# ═══════════════════════════════════════════════════════════════════

set -e

MODEL_NAME="meta-llama/Llama-3.2-3B-Instruct"
# Ungated mirror — works without HuggingFace auth
MODEL_NAME_FALLBACK="unsloth/Llama-3.2-3B-Instruct"
OUTPUT_DIR="$HOME/nexustrader-llama-finetuned"
DATASET_FILE="$HOME/nexustrader/fine_tuning_data.jsonl"
VENV_DIR="$HOME/llama-finetune-venv"
TRAIN_SCRIPT="$HOME/llama_finetune_train.py"

echo "╔══════════════════════════════════════════════╗"
echo "║  NexusTrader LLaMA LoRA Fine-Tuning (CPU)   ║"
echo "╚══════════════════════════════════════════════╝"
echo "Model:    $MODEL_NAME"
echo "Output:   $OUTPUT_DIR"
echo "Dataset:  $DATASET_FILE"
echo "RAM:      128GB (sufficient for 3B fp32)"
echo "Time:     ~4-12 hours"
echo ""

# ── Check dataset ──
if [ ! -f "$DATASET_FILE" ]; then
    echo "ERROR: Dataset not found at $DATASET_FILE"
    exit 1
fi

CONVOS=$(wc -l < "$DATASET_FILE")
echo "Dataset: $CONVOS conversations"
echo ""

# ── Setup venv ──
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating Python venv..."
    python3 -m venv "$VENV_DIR"
fi
source "$VENV_DIR/bin/activate"

# ── Install deps ──
echo "Installing Python dependencies (this may take 5-10 min)..."
pip install --upgrade pip -q 2>&1 | tail -1
pip install torch --index-url https://download.pytorch.org/whl/cpu -q 2>&1 | tail -3
pip install transformers datasets accelerate peft sentencepiece -q 2>&1 | tail -3
echo "Dependencies ready."
echo ""

# ── Write training script ──
cat > "$TRAIN_SCRIPT" << 'PYEOF'
import torch
import json
import os
import sys
from datasets import Dataset
from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM,
    TrainingArguments,
    Trainer,
    DataCollatorForLanguageModeling,
)
from peft import LoraConfig, get_peft_model, TaskType

MODEL_NAME = os.environ.get("MODEL_NAME", "unsloth/Llama-3.2-3B-Instruct")
OUTPUT_DIR = os.environ["OUTPUT_DIR"]
DATASET_FILE = os.environ["DATASET_FILE"]

print(f"PyTorch version: {torch.__version__}")
print(f"Device: {torch.cuda.is_available() and 'CUDA' or 'CPU'}")
print(f"Model: {MODEL_NAME}")
print()

# ── Load dataset ──
print("📊 Loading dataset...")
conversations = []
with open(DATASET_FILE, 'r') as f:
    for line in f:
        conversations.append(json.loads(line.strip()))

def format_llama3_chat(conv):
    """Format ShareGPT conversation to Llama 3.2 chat template."""
    parts = []
    for msg in conv['messages']:
        role = msg['role']
        content = msg['content']
        if role == 'system':
            parts.append(f"<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n\n{content}<|eot_id|>")
        elif role == 'user':
            parts.append(f"<|start_header_id|>user<|end_header_id|>\n\n{content}<|eot_id|>")
        elif role == 'assistant':
            parts.append(f"<|start_header_id|>assistant<|end_header_id|>\n\n{content}<|eot_id|>")
    return "".join(parts)

texts = [format_llama3_chat(c) for c in conversations]
dataset = Dataset.from_dict({'text': texts})
print(f"  {len(dataset)} training examples")
print(f"  Total chars: {sum(len(t) for t in texts):,}")

# ── Load tokenizer ──
print("🔤 Loading tokenizer...")
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
tokenizer.pad_token = tokenizer.eos_token

def tokenize(examples):
    return tokenizer(
        examples['text'],
        truncation=True,
        max_length=2048,
        padding='max_length',
    )

tokenized = dataset.map(tokenize, batched=True, remove_columns=['text'])
print(f"  Tokenized: {len(tokenized)} examples @ max 2048 tokens")

# ── Load model in float32 (no quantization — pure CPU) ──
print("🧠 Loading model (float32, CPU)...")
print("  This loads ~12GB into RAM. Stand by...")
model = AutoModelForCausalLM.from_pretrained(
    MODEL_NAME,
    torch_dtype=torch.float32,
    device_map='cpu',
    low_cpu_mem_usage=True,
    trust_remote_code=False,
)
print(f"  Model loaded: {sum(p.numel() for p in model.parameters()):,} params")

# ── Apply LoRA (only trains ~0.1% of params) ──
print("🎯 Applying LoRA adapters...")
lora_config = LoraConfig(
    task_type=TaskType.CAUSAL_LM,
    r=4,                     # Lower rank for CPU efficiency
    lora_alpha=8,
    lora_dropout=0.05,
    target_modules=['q_proj', 'v_proj'],  # Only Q and V projections (fewer params)
    bias='none',
)

model = get_peft_model(model, lora_config)
trainable, total = model.get_nb_trainable_parameters()
print(f"  Trainable: {trainable:,} / {total:,} ({100*trainable/total:.2f}%)")

# Freeze base model (already done by PEFT, but be explicit)
for name, param in model.named_parameters():
    if 'lora' not in name:
        param.requires_grad = False

# ── Training ──
print("🏋️ Starting training...")
print("  ETA: 4-12 hours on CPU. Progress every 5 steps.")
training_args = TrainingArguments(
    output_dir=OUTPUT_DIR,
    num_train_epochs=3,
    per_device_train_batch_size=1,
    gradient_accumulation_steps=4,   # Effective batch = 4
    learning_rate=2e-4,
    warmup_steps=5,
    logging_steps=5,
    save_steps=25,
    save_total_limit=2,
    fp16=False,
    bf16=False,
    optim='adamw_torch',
    report_to='none',
    dataloader_num_workers=0,
    logging_dir=os.path.join(OUTPUT_DIR, 'logs'),
)

data_collator = DataCollatorForLanguageModeling(
    tokenizer=tokenizer,
    mlm=False,
)

trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=tokenized,
    data_collator=data_collator,
)

trainer.train()

# ── Save ──
print("💾 Saving fine-tuned model...")
os.makedirs(OUTPUT_DIR, exist_ok=True)
model.save_pretrained(OUTPUT_DIR)
tokenizer.save_pretrained(OUTPUT_DIR)

# Save training config
with open(os.path.join(OUTPUT_DIR, 'training_info.json'), 'w') as f:
    json.dump({
        'base_model': MODEL_NAME,
        'num_examples': len(conversations),
        'epochs': 3,
        'lora_rank': 4,
        'lora_alpha': 8,
        'learning_rate': 2e-4,
        'method': 'LoRA (CPU float32)',
    }, f, indent=2)

print()
print("╔══════════════════════════════════════════╗")
print("║  FINE-TUNING COMPLETE! 🍌🍌🍌          ║")
print(f"║  Saved to: {OUTPUT_DIR}")
print("╚══════════════════════════════════════════╝")
print()
print("Next steps:")
print(f"  1. Merge LoRA: python3 merge_lora.py {OUTPUT_DIR}")
print(f"  2. Convert to GGUF for llama.cpp")
print(f"  3. Update llama-server to use new model")
print("  Or just use the LoRA adapters directly with HuggingFace transformers.")
PYEOF

# Run training
echo "Starting training..."
echo "This will take 4-12 hours. Output saved to $OUTPUT_DIR"
echo "Logs at $OUTPUT_DIR/logs/"
echo ""

export MODEL_NAME="$MODEL_NAME_FALLBACK"
export OUTPUT_DIR="$OUTPUT_DIR"
export DATASET_FILE="$DATASET_FILE"

python3 "$TRAIN_SCRIPT" 2>&1 | tee "$OUTPUT_DIR/training.log"

echo ""
echo "DONE! 🍌"
echo "Model saved to $OUTPUT_DIR"
