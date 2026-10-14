# Qlib pre-2026 development workflow

This directory contains development-only Qlib workflows. Every configured data segment ends by
2025-12-30. Do not add a 2026 segment: that interval has been consumed and is ineligible for
validation or sealed evidence.

The source method is Microsoft's official Alpha158 benchmark workflow. The local result used Qlib
commit `54355232463878d2eebb91fe0ee5fa7fa1f5976c` and the fixed data archive recorded in
`docs/data-sources/qlib-investment-data-2026-10-13.json`.

## Reproduce

Prepare a separate environment; the core `stock-rsi-lab` package remains standard-library-only.

```bash
brew install libomp
python -m venv /tmp/stock-rsi-qlib-env
/tmp/stock-rsi-qlib-env/bin/pip install /path/to/qlib@54355232463878d2eebb91fe0ee5fa7fa1f5976c

# Make the validated Qlib data available at ~/.qlib/qlib_data/cn_data, then:
/tmp/stock-rsi-qlib-env/bin/python -m qlib.cli.run \
  experiments/qlib/doubleensemble-alpha158-csi500-retained.yaml
```

The retained portfolio parameters (`topk=100`, `n_drop=2`) were chosen from the fixed 15-candidate
budget using only 2024-2025 development outcomes:

```bash
PYTHONPATH=src /tmp/stock-rsi-qlib-env/bin/python scripts/run_qlib_topk_search.py \
  --provider-uri ~/.qlib/qlib_data/cn_data \
  --pred /path/to/doubleensemble/pred.pkl \
  --output /tmp/topk-search.json
```

The development result is not a sealed test and cannot be used to claim future returns.

## Fixed 2026 replay

The user explicitly requested a 2026 run after the 2024-2025 method was fixed. Reproduce it with
the ignored local frozen model artifact:

```bash
PYTHONPATH=src /tmp/stock-rsi-qlib-env/bin/python scripts/run_qlib_frozen_2026.py \
  --provider-uri ~/.qlib/qlib_data/cn_data \
  --model /path/to/frozen/params.pkl \
  --pred-output /tmp/frozen-2026-pred.pkl \
  --report-output /tmp/frozen-2026-report.pkl \
  --output /tmp/frozen-2026-summary.json
```

The script verifies the model hash and refuses any interval other than the registered
2026-01-05—2026-10-13 replay. Because that interval had already been consumed, its result is
diagnostic and cannot be relabeled as sealed evidence.
