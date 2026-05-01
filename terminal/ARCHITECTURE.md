# Securatron Security Interface — Architecture Document

## First Principles Analysis

### Core Question: What is a security interface?

A security interface is fundamentally an **information transformation pipeline**:

```
Raw Data → Ingestion → Processing → Intelligence → Action
```

Each stage transforms data into a higher-value form. The interface is the system that orchestrates this transformation.

### Component Decomposition

```
┌─────────────────────────────────────────────────────────────┐
│                    SECURITY INTERFACE                        │
│                                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │ INGEST   │  │ PROCESS  │  │ OUTPUT   │  │ CONTROL  │   │
│  │          │  │          │  │          │  │          │   │
│  │ Text     │  │ LLM      │  │ Text     │  │ Voice    │   │
│  │ Audio    │  │ Reason   │  │ Image    │  │ Click    │   │
│  │ Image    │  │ Analyze  │  │ Audio    │  │ Keyboard │   │
│  │ Scan     │  │ Correlat │  │ Visual   │  │ API      │   │
│  │          │  │ Synthesize│ │ Charts   │  │          │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
│                                                              │
│  ┌─────────────────────────────────────────────────────────┐│
│  │              MODEL MANAGEMENT LAYER                      ││
│  │  ┌────────┐  ┌────────┐  ┌───────┐  ┌───────┐         ││
│  │  │ LLM    │  │ Image  │  │ STT   │  │ TTS   │         ││
│  │  │ Qwen3.6│  │ Flux   │  │ Whisper│  │ Kokoro│         ││
│  │  └────────┘  └────────┘  └───────┘  └───────┘         ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

### Efficiency Principles

1. **Minimize Model Swapping**: Swapping models costs 10-60 seconds. The interface should use the loaded model for as many tasks as possible.
2. **Pipeline Parallelism**: While the LLM processes one request, the image model can generate visuals for the previous result.
3. **Result Caching**: Common analyses (e.g., "summarize this scan") should be cached.
4. **Streaming**: Text output should stream in real-time, not wait for the full response.
5. **Graceful Degradation**: If one model fails, the interface should still function with reduced capability.

### Architecture: The Security Operations Loop

```
                    ┌─────────┐
                    │  INPUT  │
                    └────┬────┘
                         │
                    ┌────▼────┐
                    │  INGEST │  (Multi-modal)
                    └────┬────┘
                         │
                    ┌────▼────┐
                    │  ROUTE  │  (Determine which model to use)
                    └────┬────┐
                         │    │
                    ┌────▼┐  │
                    │LLM│  ┌▼──────┐
                    └──┬┘  │IMAGE │
                       │   └──────┘
                    ┌────▼────┐
                    │  FORMAT │  (Text, Image, Audio)
                    └────┬────┘
                         │
                    ┌────▼────┐
                    │  PRESENT│  (Dashboard, Voice, Visual)
                    └────┬────┘
                         │
                    ┌────▼────┐
                    │  FEEDBACK│ ← User can interrupt, redirect, refine
                    └─────────┘
```

### Model Strategy

**Currently Loaded:**
- LLM: Qwen3.6-35B-A3B (GPU) - General reasoning, analysis
- Image: Flux-2-Klein-4B (GPU) - Visual generation
- STT: Whisper-Large-v3-Turbo (GPU) - Speech-to-text
- TTS: kokoro-v1 (CPU) - Text-to-speech

**Strategy:** Keep all four loaded. The interface is designed to use them all without swapping. Model swapping only happens when we need a fundamentally different LLM capability (e.g., Gemma for vision understanding).

### System Constraints

- **1 model per category** can be loaded simultaneously
- GPU memory is shared between LLM and Image models
- CPU has 32 cores, 32GB RAM
- Network: Localhost only (no external calls)

## Implementation Plan

### Phase 1: Foundation (Done)
- [x] Model manager CLI
- [x] Basic recon dashboard
- [x] Voice transcription pipeline
- [x] Image generation pipeline

### Phase 2: Security Interface (In Progress)
- [ ] Threat analysis dashboard
- [ ] Multi-modal input handling
- [ ] Real-time streaming
- [ ] Security persona system

### Phase 3: Intelligence Layer
- [ ] Scan result analysis
- [ ] Threat correlation
- [ ] Actionable recommendations
- [ ] Report generation

### Phase 4: Polish
- [ ] Visual polish (CRT aesthetic, animations)
- [ ] Voice commands (hands-free)
- [ ] Keyboard shortcuts
- [ ] Performance optimization

## File Structure

```
~/.securatron/terminal/
├── ARCHITECTURE.md          # This file
├── index.html               # Fallout CRT terminal (original)
├── recon-dashboard.html     # Multi-modal recon dashboard
├── security-interface.html  # Main security operations center
└── scripts/
    ├── analyze.py           # Security analysis tools
    ├── correlate.py         # Threat correlation engine
    └── report.py            # Report generation
```

## Key Design Decisions

1. **Single HTML file** for the main interface - easy to serve, edit, and share
2. **REST API** for all model interactions - decoupled from the UI
3. **Streaming responses** for real-time feedback
4. **Modular JavaScript** - each feature is a self-contained module
5. **First-principles routing** - input is analyzed to determine the best processing path

## Red-Light Protocols (Stop Conditions)

To ensure system stability and data integrity, the interface must adhere to the following stop-and-report triggers:

1. **Latency Threshold**: If WebSocket round-trip time (RTT) exceeds 1000ms for 3 consecutive packets, STOP and revert to HTTP long-polling.
2. **Model Sync Mismatch**: If the health-check model slug does not match the active session slug, STOP and re-verify the model manager state.
3. **Hardware Exhaustion**: If GPU memory utilization reaches 98% or system RAM free space drops below 512MB, STOP and evict the least recently used (LRU) model.
4. **Validation Failure**: If any of the 8 core health checks fail, HALT all active tool-chains and display the failure state on the main dashboard.
5. **Unauthorized Scope**: If a command is issued against a target not present in the active project's `scope.yaml`, the interface must hard-refuse the execution.

**Doctrine Reference**: These protocols derive from the SecuraTron First Principles Loop (fp-loop) and the Identity of the Memory Organ Charter.
