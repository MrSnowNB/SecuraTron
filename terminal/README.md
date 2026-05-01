# SecuraTron SOC Interface (Terminal)

## Overview

The Terminal is the multi-modal front-end for the SecuraTron harness. It provides a visual and voice-driven interface for human operators to monitor, direct, and audit the autonomous activities of the underlying engine.

## Integration with SecuraTron

The Terminal acts as a high-level **Outer Builder** and observer:
1. **Visualization:** Renders real-time telemetry from `lemond` and the `mcp_server`.
2. **Monitoring:** Provides a live view of the **Self-Improvement Loop** and active **Molecule** executions.
3. **Control:** Allows for manual "Human Gate" approvals for destructive molecules.
4. **Audit:** Displays trial ledgers and post-mortem findings in a readable dashboard format.

## Architecture

### First Principles

A security interface is fundamentally an **information transformation pipeline**:
```
Raw Data → Ingestion → Processing → Intelligence → Action
```

### Components

| Component | Model | Device | Purpose |
|-----------|-------|--------|---------|
| LLM | Qwen3.6-35B-A3B | GPU | Analysis, reasoning, generation |
| Image | Flux-2-Klein-4B | GPU | Network diagrams, visualizations |
| STT | Whisper-Large-v3-Turbo | GPU | Speech-to-text (voice input) |
| TTS | kokoro-v1 | CPU | Text-to-speech (voice output) |

### Model Management

- **Constraint**: Only 1 model per category can be loaded simultaneously
- **Strategy**: Keep all 4 models loaded. Interface designed to use them all without swapping
- **Swapping**: Only swap LLM when fundamentally different capability is needed

### Efficiency Principles

1. **Minimize model swapping** (costs 10-60s per swap)
2. **Pipeline parallelism** — LLM processes while image model generates visuals
3. **Result caching** — Common analyses are cached
4. **Streaming output** — Text streams in real-time
5. **Graceful degradation** — Interface functions with reduced capability

## File Structure

```
~/.securatron/terminal/
├── README.md                    # This file
├── ARCHITECTURE.md              # Detailed architecture document
├── security-interface.html      # Main SOC dashboard (v2.0)
├── index.html                   # Original Fallout CRT terminal
├── recon-dashboard.html         # Multi-modal recon dashboard
└── scripts/
    ├── analyze.py               # Threat analysis engine
    ├── correlate.py             # Threat correlation engine
    └── report.py                # Report generation
```

## Usage

### Launch the Interface

```bash
# The interface is served at http://localhost:8080/security-interface.html
# The HTTP server should already be running from the previous session
```

### Voice Commands

1. Click the 🎤 VOICE button (or Ctrl+M)
2. Speak your command
3. Whisper transcribes your speech
4. LLM processes it with the active persona
5. TTS reads the response (optional)

### Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| Ctrl+Enter | Execute command |
| Ctrl+M | Toggle voice input |
| Ctrl+C | Clear terminal |
| Ctrl+A | Analyze threats |

### Personas

| Persona | Mode | Purpose |
|---------|------|---------|
| Analyst | [A] | Threat analysis, vulnerability assessment |
| Operator | [O] | Active recon, scanning, exploitation |
| Commander | [C] | Strategic overview, risk assessment |

### CLI Tools

```bash
# Analyze scan results
python3 scripts/analyze.py scan /path/to/scan.json

# Analyze threat text
python3 scripts/analyze.py threat "SQL injection in login form"

# Analyze attack surface
python3 scripts/analyze.py surface "192.168.1.100"

# Correlate security events
python3 scripts/correlate.py events /path/to/events.json

# Generate security report
python3 scripts/report.py generate "192.168.1.100"
```

### Model Management

```bash
# Check model status
python3 /home/mark/.securatron/bin/model_manager.py status

# List all models
python3 /home/mark/.securatron/bin/model_manager.py list

# Swap LLM model
python3 /home/mark/.securatron/bin/model_manager.py swap Gemma-4-31B-it-GGUF
```

## API Endpoints

The lemonade server exposes these endpoints:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/v1/chat/completions` | POST | LLM chat |
| `/v1/images/generations` | POST | Image generation |
| `/v1/audio/speech` | POST | Text-to-speech |
| `/v1/audio/transcriptions` | POST | Speech-to-text |
| `/api/v1/health` | GET | Server health |
| `/v1/models` | GET | Model list |

## Security Considerations

- All models run locally — no external calls
- Voice input is processed locally via Whisper
- Image generation uses local Flux model
- No data leaves the machine

## Future Improvements

- [ ] Real-time scan integration (Nmap, Nikto)
- [ ] Multi-agent collaboration
- [ ] Automated report generation
- [ ] Threat intelligence feeds
- [ ] Dashboard persistence
- [ ] WebSocket streaming for real-time output
- [ ] Mobile responsive design
- [ ] Dark/light theme toggle
- [ ] Export to PDF
- [ ] Integration with SIEM tools

## Credits

Built on the Securatron harness by Mark. First Principles Architecture v1.0.
