# PDF source-test CI dependency correction

The push of `faf9434ee92c19ec1299f0c9206708376b23fd30` failed all three
GitHub Actions jobs (run39685302539). The new whole-corpus regression imports
`pypdf`, while `requirements-test.txt` declared only BeautifulSoup. Local
validation had explicitly loaded an already bundled PDF package and therefore
did not validate the clean CI dependency declaration. Public API annotations
showed failed test steps; unauthenticated full-log downloads returned403.

The exact CI-style unittest discovery command was reproduced locally without
that bundled-package bootstrap:1051 tests, one import error in
`test_profitability_all_v6`, `ModuleNotFoundError: No module named 'pypdf'`.
The fix adds `pypdf==6.10.0` to the shared test requirements, matching the
registered source extractor. No tests were removed, skipped or weakened;
notifications/workflow triggers were not disabled. No local package install.
Frozen source protocols, prior failures and raw originals are unchanged.

With the already available6.10.0 package, the full local suite passed1054 tests.
After pushing fix `f49a82664757e7c357d04aa219eaa7bf1c9a1276`, GitHub run
[39685759553](https://github.com/shouldnotappearcalm/stock-rsi-lab/actions/runs/39685759553)
completed successfully for `unittest (3.11)`, `unittest (3.12)` and
`research-tests`. These clean hosted environments installed the declared
requirements and ran full discovery. This confirms the CI correction, not any
investment return or financial-data admission.
