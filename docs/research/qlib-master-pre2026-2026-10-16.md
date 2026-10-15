# Source-pinned MASTER A-share development probe

After the fixed DE+TRA blend failed, one independent model family was prepared from the official [MASTER source](https://github.com/SJTU-DMTai/MASTER) at `de8f58557096abde4216a701b35fc4368158d111`. Its market-state gate and cross-stock attention differ from both DoubleEnsemble and TRA. The training and replay script, hashes and budget were frozen at `6f5c70d` before seeing this portfolio result.

The local data preparation reconstructed 63 index-market features from CSI300, CSI500 and CSI800 and a 1,211,745-row CSI500 Alpha158 stock panel. Market and stock normalizers were fitted only through 2021-12-29. The model trained on labels from dates through 2021-12-23; the last such five-session label matured on 2021-12-30. Validation and development label tails matured on 2023-12-29 and 2025-12-30. Each prediction uses that stock's last eight observed sessions, their same-date market features, and the official MASTER network. Qlib's TopK strategy consumes the preceding session's signal for the current trade day.

Seed 0, 10 epochs at most, 480 sampled training dates per epoch, learning rate `8e-6`, training-loss stop at `0.95`, Top100/Drop2, 95% risk degree and the Qlib exchange costs were fixed in advance. The stop threshold was not reached; final training loss was `0.9997` after all 4,800 steps. The 2024-01-02—2025-12-23 development replay and an unchanged DE control used the same 479 trading sessions.

| Metric | MASTER | Same-date DE control |
| --- | ---: | ---: |
| 2024 net return | 4.79% | **11.47%** |
| 2025 net return | 20.02% | **41.89%** |
| Net annualized | 12.30% | **26.13%** |
| Two-year net compound | 25.76% | **58.17%** |
| CSI500 compound | 33.66% | 33.66% |
| Compound excess | -7.90 pp | **+24.51 pp** |
| Maximum drawdown | -20.16% | -20.12% |
| Average exposure | 99.75% | 99.58% |
| Cost / initial capital | 2.02% | 2.22% |

The fixed candidate missed the 20% annualized and 2024 yearly targets and underperformed both DE and the index. This does not prove the published MASTER architecture is weak: this local adaptation uses CSI500, a bounded 4,800-step training budget and our fixed portfolio rather than the paper's original setup. It does show that this **specific reproducible candidate** is not a solution. No extra epochs, learning-rate changes or portfolio variants were selected after seeing the result, and the consumed 2026 interval was not queried.

The [machine result](../../experiments/qlib/master-pre2026-results.json) includes all ten training losses, source/data/model/prediction/report hashes, and the exact same-date control. The Qlib historical archive still has incomplete PIT security-state and corporate-action proof; close execution and simplified price limits also constrain the backtest. The repeatedly inspected 2024–2025 period remains development evidence only.
