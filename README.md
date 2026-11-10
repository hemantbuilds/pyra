# Pyra

Personal AI operating system for Linux, built around Mark-LIII on a Raspberry Pi.

**Flow:** Mark-LIII → Dot → PYRA Master → Project OS / Device Broker / Engineering OS

**Docs:** [`docs/architecture/`](docs/architecture/) · [`docs/implementation/`](docs/implementation/) · [Project OS](docs/implementation/PROJECT_OS.md) · [Device Broker](docs/implementation/DEVICE_BROKER.md) · [Engineering OS](docs/implementation/ENGINEERING_OS.md)

```bash
# Mark face
cd Mark-LIII && python setup.py && python main.py

# PYRA Master + Dot + Project OS + Device Broker + Engineering OS
cd agent-os && .venv/bin/python -m master

# Optional: Device Broker as standalone MCP stdio server
cd agent-os && .venv/bin/python -m device_broker

# Tests
agent-os/.venv/bin/python -m pytest \
  tests/master tests/project_os tests/device_broker tests/engineering_os -q
```

Secrets stay local (`config/api_keys.json` is gitignored).
