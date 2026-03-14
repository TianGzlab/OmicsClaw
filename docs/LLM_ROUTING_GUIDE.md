# LLM-Based Query Routing Guide

## Quick Start

1. Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

2. Edit `.env` and set your configuration:
```bash
LLM_PROVIDER=deepseek
LLM_API_KEY=sk-your-api-key-here
```

3. Run any orchestrator with `--routing-mode llm`:
```bash
python skills/orchestrator/omics_orchestrator.py --demo --output /tmp/test --routing-mode llm
```

That's it! The orchestrator will automatically load your .env configuration.

## Overview

OmicsClaw orchestrators support three routing modes:
- **keyword**: Fast, free, pattern-based matching (default)
- **llm**: Intelligent semantic routing via LLM API (requires API key)
- **hybrid**: Keyword first, LLM fallback if confidence < 0.5

## Supported Providers

### DeepSeek (Recommended)
```bash
export DEEPSEEK_API_KEY="sk-..."
export LLM_BASE_URL="https://api.deepseek.com/v1"
export LLM_MODEL="deepseek-chat"
```

### OpenAI
```bash
export OPENAI_API_KEY="sk-..."
export LLM_BASE_URL="https://api.openai.com/v1"
export LLM_MODEL="gpt-4o-mini"
```

### Custom (OpenAI-compatible)
```bash
export LLM_API_KEY="your-key"
export LLM_BASE_URL="https://your-api.com/v1"
export LLM_MODEL="your-model"
```

## Usage Examples

### Single-Cell Orchestrator
```bash
# Keyword routing (default)
python skills/singlecell/orchestrator/sc_orchestrator.py \
  --demo --output /tmp/sc --routing-mode keyword

# LLM routing
python skills/singlecell/orchestrator/sc_orchestrator.py \
  --demo --output /tmp/sc --routing-mode llm

# Hybrid routing
python skills/singlecell/orchestrator/sc_orchestrator.py \
  --demo --output /tmp/sc --routing-mode hybrid
```

### Top-Level Omics Orchestrator
```bash
# Routes across all 5 domains with LLM
python skills/orchestrator/omics_orchestrator.py \
  --demo --output /tmp/omics --routing-mode llm
```

### All Domain Orchestrators
All orchestrators support `--routing-mode`:
- `skills/singlecell/orchestrator/sc_orchestrator.py`
- `skills/genomics/orchestrator/genomics_orchestrator.py`
- `skills/proteomics/orchestrator/proteomics_orchestrator.py`
- `skills/metabolomics/orchestrator/metabolomics_orchestrator.py`
- `skills/orchestrator/omics_orchestrator.py`

## Configuration Priority

1. Provider-specific keys: `DEEPSEEK_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`
2. Generic key: `LLM_API_KEY`
3. Auto-detection from base URL if key is set

## Performance Comparison

| Mode | Speed | Accuracy | Cost |
|------|-------|----------|------|
| keyword | Fast (instant) | Good for exact matches | Free |
| llm | Moderate (1-2s per query) | Excellent for complex queries | ~$0.0001/query |
| hybrid | Fast for known patterns | Best of both | Minimal cost |

## Testing

Tested with DeepSeek API on 2026-03-14:
- ✅ Single-cell orchestrator: 6/6 queries routed correctly
- ✅ Omics orchestrator: 30/30 queries across 5 domains routed correctly
- ✅ Confidence scores: 0.95 for all LLM-routed queries
