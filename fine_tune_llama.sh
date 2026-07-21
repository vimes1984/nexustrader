#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════
# NexusTrader LLaMA Fine-Tuning Pipeline
# ═══════════════════════════════════════════════════════════════════
# Fine-tunes Llama 3.2 3B Instruct on NexusTrader trading data
# using QLoRA (4-bit quantization) — runs on CPU (chris-System, 128GB RAM)
#
# Usage:
#   chmod +x fine_tune_llama.sh
#   ./fine_tune_llama.sh
#
# Output: ~/nexustrader-llama-finetuned/
# ═══════════════════════════════════════════════════════════════════

set -e

MODEL_NAME="NousResearch/Llama-3.2-3B-Instruct"
OUTPUT_DIR="$HOME/nexustrader-llama-finetuned"
DATASET_FILE="$HOME/nexustrader/fine_tuning_data.jsonl"
VENV_DIR="$HOME/llama-finetune-venv"

echo "╔══════════════════════════════════════════════╗"
echo "║  NexusTrader LLaMA QLoRA Fine-Tuning        ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
echo "Model:    $MODEL_NAME"
echo "Output:   $OUTPUT_DIR"
echo "Dataset:  $DATASET_FILE"
echo "Hardware: CPU (128GB RAM), no GPU"
echo ""

# ── Check dataset exists ──
if [ ! -f "$DATASET_FILE" ]; then
    echo "ERROR: Dataset not found at $DATASET_FILE"
    echo "Run build_finetune_dataset.py first!"
    exit 1
fi

CONVOS=$(wc -l < "$DATASET_FILE")
echo "Dataset: $CONVOS conversations"

# ── Setup Python venv ──
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating Python venv..."
    python3 -m venv "$VENV_DIR"
fi
source "$VENV_DIR/bin/activate"

# ── Install dependencies ──
echo "Installing dependencies (this may take a while)..."
pip install --upgrade pip -q
pip install torch --index-url https://download.pytorch.org/whl/cpu -q
pip install transformers datasets accelerate peft bitsandbytes sentencepiece -q
echo "Dependencies installed."

# ── Run fine-tuning ──
echo ""
echo "Starting QLoRA fine-tuning..."
echo "This will take 2-8 hours on CPU. Go grab a banana. 🍌"
echo ""

python3 -c "
import torch
import json
from datasets import Dataset
from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM,
    TrainingArguments,
    Trainer,
    BitsAndBytesConfig,
    DataCollatorForLanguageModeling,
)
from peft import (
    LoraConfig,
    get_peft_model,
    prepare_model_for_kbit_training,
    TaskType,
)
import os

# ── Config ──
MODEL_NAME = '$MODEL_NAME'
OUTPUT_DIR = '$OUTPUT_DIR'
DATASET_FILE = '$DATASET_FILE'

# ── Load dataset ──
print('Loading dataset...')
conversations = []
with open(DATASET_FILE, 'r') as f:
    for line in f:
        conversations.append(json.loads(line.strip()))

# Convert ShareGPT format to text
def format_conversation(conv):
    parts = []
    for msg in conv['messages']:
        role = msg['role']
        content = msg['content']
        if role == 'system':
            parts.append(f'<|system|>\\n{content}</s>')
        elif role == 'user':
            parts.append(f'<|user|>\\n{content}</s>')
        elif role == 'assistant':
            parts.append(f'<|assistant|>\\n{content}</s>')
    return '\\n'.join(parts)

texts = [format_conversation(c) for c in conversations]
dataset = Dataset.from_dict({'text': texts})
print(f'Loaded {len(dataset)} training examples')

# ── Load tokenizer ──
print('Loading tokenizer...')
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
print(f'Tokenized: {len(tokenized)} examples')

# ── Load model with 4-bit quantization ──
print('Loading model with 4-bit quantization...')
bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type='nf4',
    bnb_4bit_compute_dtype=torch.float32,  # CPU safe
    bnb_4bit_use_double_quant=True,
)

model = AutoModelForCausalLM.from_pretrained(
    MODEL_NAME,
    quantization_config=bnb_config,
    device_map='cpu',   # Force CPU
    torch_dtype=torch.float32,
    trust_remote_code=False,
)
model = prepare_model_for_kbit_training(model)

# ── Apply LoRA ──
print('Applying LoRA adapters...')
lora_config = LoraConfig(
    task_type=TaskType.CAUSAL_LM,
    r=8,                    # LoRA rank
    lora_alpha=16,          # LoRA alpha
    lora_dropout=0.05,      # Dropout for regularization
    target_modules=['q_proj', 'k_proj', 'v_proj', 'o_proj'],  # Attention layers
    bias='none',
)

model = get_peft_model(model, lora_config)
print(f'Trainable params: {model.get_nb_trainable_parameters()}')

# ── Training ──
print('Starting training...')
training_args = TrainingArguments(
    output_dir=OUTPUT_DIR,
    num_train_epochs=3,
    per_device_train_batch_size=1,   # CPU: batch size 1
    gradient_accumulation_steps=8,   # Effective batch = 8
    learning_rate=2e-4,
    warmup_ratio=0.1,
    logging_steps=5,
    save_steps=50,
    save_total_limit=2,
    fp16=False,
    bf16=False,
    optim='adamw_torch',
    report_to='none',
    dataloader_num_workers=0,
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
print('Saving model...')
model.save_pretrained(OUTPUT_DIR)
tokenizer.save_pretrained(OUTPUT_DIR)

print()
print('╔══════════════════════════════════════════════╗')
print('║  FINE-TUNING COMPLETE! 🍌                   ║')
print(f'║  Model saved to: {OUTPUT_DIR}  ║')
print('╚══════════════════════════════════════════════╝')
print()
print('To use with llama.cpp:')
print(f'  1. Convert: python3 llama.cpp/convert.py {OUTPUT_DIR}')
print(f'  2. Quantize: llama.cpp/quantize ...')
print(f'  3. Run: ./llama-server -m {OUTPUT_DIR}/ggml-model-Q4_K_M.gguf')
print()
"

echo ""
echo "Done! Model saved to $OUTPUT_DIR"
echo "Update llama-server to point at the new model."
