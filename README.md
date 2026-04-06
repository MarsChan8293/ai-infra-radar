# ai-infra-radar

## Bootstrap

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Run the health app

```bash
uvicorn radar.main:app --reload
# GET http://localhost:8000/health
```

## Run tests

```bash
python3 -m pytest
```

## Validate config

```bash
python3 -m radar.cli validate-config tests/fixtures/minimal.yaml
```
