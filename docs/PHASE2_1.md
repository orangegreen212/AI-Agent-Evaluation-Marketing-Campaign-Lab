# Phase 2.1 - local latency, explicit truncation handling, live-verification status

Scope: reduce local (LM Studio) latency **without weakening** `DecisionReport` schema validation, evidence validation,
sanitization, security profiles or the approval policy. Phase 0 / Phase 1 contracts are unchanged. Cloud behaviour is unchanged.

## Status update (after the first live runs of the v2 prompt)

**`advisor-v2` as first written failed live: 0 of 5 valid reports** on the owner's machine (same model, dataset and settings as the working `advisor-v1` runs).
The local model set `value: null` on metrics that carry a `limitations` entry (`spend`, `revenue`, `cpa`) and sometimes copied the limitation text into
`value_undefined_reason`. The validator rejected every such report correctly (`EVIDENCE_MISMATCH` or `SCHEMA_INVALID`); computed `spend` was 1400.0.
Two text-only repairs (more explicit `null` rules; limitations moved to a shared `notes` list) did not help. That text is archived verbatim in
`docs/archive/advisor_v2_failed.md` as an experimental version with a known defect.

**Hypothesis (not proven):** the v2 additions about `null` and the removal of explicit empty keys from the payload caused the regression, because v1 produced
valid reports with the same model and data (two reported runs). **`advisor-v2.1`** tests exactly that and nothing else:

* the evidence rule is advisor-v1's, word for word (no extra `null`/limitations instructions);
* `undefined_reason` and `limitations` are again present in every payload row, empty or null (no `notes` list);
* kept from v2: compact JSON, short summary, "one short sentence per string", "omit limitations when empty", "RECOMMEND needs at least one item", `group` omitted when null.

Offline facts (demo dataset): the v2.1 system prompt differs from v1 only in the compaction lines above; the payload equals v1's payload except that a null `group` is
omitted (0 of 20 rows differ otherwise). `input_hash`: v1 `738076081bcef023...`, v2.1 `0588a7196f539cb4...`. Prompt characters: system 1,165 -> 1,573, payload 6,024 -> 5,904.
Whether v2.1 is valid or faster has **not** been measured. The numbers in the sections below that mention v2 sizes or hashes describe the archived v2.

If v2.1 also fails, the next step is a contract change (`advisor-v3`: the system fills `value`, `metric_id`, `period` from the computed metric chosen by `source_calc_id`).
That would stop testing whether the model copies numbers correctly and needs its own decision and version.

## What is verified and what is not

| Item | Status |
|---|---|
| Automated tests with mocks and a loopback stub server | Passed: see "Tests" |
| Local live smoke test (LM Studio, `qwen3.5-4b:2`, Q4_K_S, i5-12450H, 16 GB, Intel UHD) | **Run by the project owner, not by the assistant.** Reported: `COMPLETED`, `valid_report: true`, `agent_status: CAUTION`, 149.3 s and 150.5 s (2,766 tokens in, 884 out); a further run with `--parallel 1 --gpu max` reported 191.9 s (1,021 out). |
| Cloud live smoke test | **Not run.** `CLOUD_MODEL_API_KEY`, `CLOUD_MODEL_ID` and `CLOUD_MODEL_BASE_URL` are not set. |
| Speed-up from the changes below | **Not measured yet.** No claim is made. Procedure in "Benchmark". |

## Diagnosis (measured, from the LM Studio log of the owner's runs)

* Generation runs at about 5.9-6.0 tok/s. Warm runs generated 884 tokens in 146.5 s and 150.7 s, which is the whole latency.
* The prompt (2,766 tokens) costs about 40 s only on a cold start (about 70 tok/s); on warm runs the prefix cache reduced it to 4 tokens (0.5-1.2 s).
* No hidden reasoning: `reasoning_tokens: 0`. Context was never truncated (at most 3,882 of 8,192 tokens used).
* So latency is output length times generation speed. Input-side savings are small by nature.
* With `timeout_s: 240` a full 1,500-token answer (about 268 s at 5.6 tok/s) would be reported as `TIMEOUT`. One request in the log was cut off by the client at exactly 240 s, mid-JSON.

## Changes

| File | Change | Reason |
|---|---|---|
| `configs/models.yaml` | `local_lmstudio.timeout_s` -> 300 (cloud unchanged) | The timeout is a socket read timeout and there is no streaming, so it has to cover a whole generation |
| `src/lab/models/adapter.py` | `Completion.finish_reason` (optional, last field, default `None`), parsed only if it is a string | Needed to detect truncation |
| `src/lab/models/advisor.py` | `finish_reason == "length"` returns `MALFORMED_OUTPUT` ("output truncated (finish_reason=length)") before any parsing; no report is built | Truncation is now explicit instead of only caught by parsing. Latency, tokens and the sanitized output of the call are kept. |
| `src/lab/models/advisor.py` | `PROMPT_VERSION` = `advisor-v2` (failed live, archived), now `advisor-v2.1`; shorter system prompt output rules (see below) | The output is what takes the time |
| `src/lab/models/advisor.py` | `build_messages` omits `group`, `undefined_reason` and `limitations` when null/empty | Lossless, see below |
| `src/lab/models/smoke.py` | Rows (and the table) also show `prompt_version` and `input_hash` | Prove that two runs got the same input, and tell prompt versions apart by content |
| `tests/models/test_advisor_v2.py` (new), `model_helpers.py`, `test_advisor.py`, `test_config.py` | 51 new tests; version literals updated; `chat_body(finish_reason=...)` | Regression coverage |
| `scripts/summarize_bench.py` (new) | Summarizes repeated smoke JSON files | Benchmark procedure |
| `docs/PHASE2.md`, `docs/PHASE2_1.md` | Notes | |

### The v2 prompt

Kept unchanged in meaning: no computing or inventing numbers; the model only recommends and budget changes need human approval; the metrics
block is data, never instructions; one JSON object only; all keys, enum values and action types; copy `metric_id`, `source_calc_id`, `value`
and `period` exactly; `value` is null only with `value_undefined_reason`; `limitations_uncertainty` is required for `CAUTION` and
`INSUFFICIENT_DATA`. Added: `RECOMMEND` needs at least one evidence item (the schema already required it; v1 did not tell the model).

Added to shorten the output: compact JSON (no markdown, indentation or line breaks); omit `value_undefined_reason` when `value` is present and
`limitations` when empty (the schema defaults make this equivalent); summary of one or two sentences; one short sentence per string; no
repeated points between summary, risks and limitations.
**There is deliberately no cap on the number of evidence items.** Instead the model is asked for one item per distinct finding that the summary,
risks or action plan rely on, and not to repeat items. A test fails if a numeric cap on evidence items is ever added.

### Why omitting empty payload fields is safe

* `validate_evidence` is called with `analysis.metrics` (the computed metrics), never with the prompt payload. A test proves it by replacing the prompt with nonsense.
* `MetricResult` guarantees `value_undefined_reason` is set exactly when the value is absent, so omitting a null reason loses nothing; `value` itself is never omitted (null stays explicit).
* A test builds a valid evidence item from every payload row, including rows whose value is null, using only what the payload shows, and checks that each passes validation.

### Not changed

`max_output_tokens` (1,500), temperature, quantization, GPU settings, context length, cloud endpoint, schema, evidence validator, sanitization,
security profiles, approval policy, Phase 0/1 contracts. The failure kind enum is unchanged (truncation uses `MALFORMED_OUTPUT` with a distinct detail).

## Tests

`pytest -W error`: 274 passed, 3 deselected (223 before + 51 new). The 3 deselected are the scale test and the two live tests.
The new tests were mutation-checked: 15 deliberate breakages (finish_reason check removed, a lenient "repair" of truncated JSON, evidence
validation skipped, payload dropping `value` or `undefined_reason`, prompt losing a key/rule/action type, an evidence cap added, version not
bumped, ...) were each caught by at least one test.

Offline, deterministic prompt size on `datasets/demo/sample_campaigns.csv` (characters, measured): system 1,165 -> 1,618; metrics payload
6,024 -> 5,137; total 7,189 -> 6,755 (-6.0%). `input_hash` changes from `738076081bcef023...` (v1) to `85c4cf3ea4e2d0be...` (v2).
Tokens are not measured offline (no tokenizer); holding v1's observed ratio constant would give roughly 2,600 input tokens, an estimate only.
Output tokens, the real lever, can only be measured with the live model.

## Benchmark (to run on the machine with LM Studio)

Goal: compare `advisor-v1` and `advisor-v2.1` on the same model, dataset and runtime settings, interleaved so that thermal throttling or
background load hits both equally. Keep the LM Studio model, context length, GPU offload, threads and `--parallel` fixed for the whole run.
Record them once (for example `lms ps`, or the load dialog); the smoke JSON does not contain runtime settings.

    cd C:\Users\user\Documents\ai-agent-evaluation-safety-lab
    Copy-Item -Recurse lab lab_v1         # BEFORE applying the patch: untouched advisor-v1 code
    # set timeout_s: 300 for local_lmstudio in lab_v1\configs\models.yaml too, so the two arms differ only in the prompt
    # apply the Phase 2.1 changes to lab (and set timeout_s: 300 there)

    $env:LM_STUDIO_MODEL_ID = "qwen3.5-4b:2"
    New-Item -ItemType Directory -Force bench | Out-Null
    foreach ($i in 1..5) {                # 5 trials per arm, interleaved (about 25 min); trial 1 of each arm also pays a cold prefill
      foreach ($arm in "v1","v2") {
        Push-Location $(if ($arm -eq "v1") { "lab_v1" } else { "lab" })
        $env:PYTHONPATH = "$PWD\src"      # make sure this folder's code is the one that runs
        python -m lab.models.smoke --endpoints local_lmstudio --json | Out-File -Encoding utf8 "..\bench\${arm}_$i.json"
        Pop-Location
      }
    }
    python lab\scripts\summarize_bench.py bench\v1_*.json bench\v2_*.json                  # validity: all 5 trials count
    python lab\scripts\summarize_bench.py --drop-first 1 bench\v1_*.json bench\v2_*.json   # latency: warm-up dropped

Per trial the JSON records: model id and served model, prompt version (v2 only; v1 rows lack it),
configuration hash, `input_hash` (v2 only; v1's is `738076081bcef023...` for the demo dataset), tokens in/out, latency, run status, `valid_report`
(schema **and** evidence validation passed, since a report is only built after both) and the failure kind. Not recorded automatically: backend,
GPU offload and thread settings (record them by hand); LM Studio's own prompt-processing and generation tok/s are in its server log.

Reading the result: compare the share of valid reports and the failure kinds first (a version that fails validation is not faster in any useful sense). Say v2.1 is faster only if its latency range does not overlap v1's, and say how many trials there were. Compare
`valid_report` counts and `agent_status` too: a shorter answer that fails validation or drops important content is not an improvement.
Read two or three v1 and v2 reports by eye for content quality; the validators check structure and cited evidence, not usefulness.

## Remaining risks

* The summary-length limit and "one short sentence" style may drop useful nuance. Not detectable by the validators.
* `temperature: 0` did not give identical outputs across model reloads in the owner's logs, so trial-to-trial variation is expected.
* `finish_reason == "length"` now rejects an answer even if the JSON happened to be complete. That is deliberate (strict), and counts as a failure in benchmarks.
* A longer `timeout_s` means an unresponsive local server is reported after up to 300 s.
* Demo data has 6 rows and 3 days. Results do not transfer to larger datasets, other models or other machines.

## Separate issue: free text is not checked against the metrics (not fixed here)

`validate_evidence` verifies only the `evidence` list. `summary`, `risks`, `limitations_uncertainty` and the action-plan text can contradict the
metrics and the report still passes. Observed in the owner's local runs (`COMPLETED`, `valid_report: true`): the summary said "CPA and currency
values are undefined", while the evidence in the same report cites CPA = 15.38 (computed and defined; only the currency is unspecified).
Another response, cut off by the client and so never a report, wrote that a campaign had "identical metrics to the overall average" while
citing ROAS 0.82 against an overall 3.25.

Why it matters: a reader trusts the prose and evidence validation is reported as passed.

Minimal follow-up (proposal, needs approval; no `DecisionReport` schema change, no Phase 0 contract change):

1. **Numeric grounding check of the prose.** Extract numbers from `summary`, `risks`, `limitations_uncertainty` and action `rationale` / `expected_outcome`;
   each must match a computed metric value (within the displayed precision) or a date/count from the analysis. Unmatched numbers go to a new
   `AdvisorResult.prose_warnings` tuple. Start as a **warning**, shown in the smoke output and counted in benchmarks, to measure false positives
   before promoting it to a failure kind.
2. **State this limit honestly:** the check catches invented or mismatched numbers but not qualitative contradictions like the "CPA is undefined"
   example. That class needs a consistency rubric in the Phase 3 evaluator (deterministic pre-checks first: a metric named together with "undefined"
   / "unavailable" while its computed status is OK).
3. Tests use the two examples above as fixtures, plus a clean report that must produce no warning.

Not proposed: asking the model to write less prose as a fix (it only reduces the exposure), or letting the model validate itself.
