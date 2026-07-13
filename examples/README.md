# Examples

Runnable examples for the `levanto` client. Each script is standalone and reads
`LEVANTO_API_KEY` from the environment.

## Setup

```bash
pip install -e .        # or: pip install levanto
export LEVANTO_API_KEY=lv_live_...
```

## Run

```bash
python examples/01_quickstart.py
python examples/02_all_kinds.py
python examples/03_batch.py
python examples/04_grounding.py
python examples/05_error_handling.py
python examples/06_custom_transport.py
```

| Script | Shows |
|---|---|
| `01_quickstart` | Client setup, `decide()` envelope, a shortcut (plus the async client) |
| `02_all_kinds` | yesno / choice / scale / sort / tags |
| `03_batch` | One document, many questions, `list[BatchItem]` |
| `04_grounding` | Web-search grounding and `grounding_meta` |
| `05_error_handling` | `ready()` and typed errors |
| `06_custom_transport` | Injecting your own httpx transport |

The Sage endpoint is scale-to-zero, so the first call after an idle period may
take ~90s to warm up.
