#!/bin/bash
# daily_agent.sh
# Runs daily parameters self-improvement and AI self-development

# Navigate to application root directory
cd "$(dirname "$0")"

echo "=========================================================="
echo "📅 Starting Daily Self-Improvement & AI Self-Dev: $(date)"
echo "=========================================================="

echo "🤖 1. Running Quant PHD Parameter Self-Improvement..."
python3 self_improvement_agent.py

echo "🤖 2. Running AI Coding Assistant Self-Development..."
python3 agent_self_developer.py

echo "=========================================================="
echo "🎉 Daily Agent tasks completed successfully!"
echo "=========================================================="
