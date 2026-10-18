"""Optional, needs real endpoints. Excluded from the normal run:  pytest -m live -s
LAB_LIVE_LOCAL=1 (LM Studio running + model loaded) and/or LAB_LIVE_CLOUD=1 (+ CLOUD_MODEL_API_KEY, CLOUD_MODEL_ID).
Cloud runs send ONLY datasets/demo/sample_campaigns.csv aggregates, under the 'benchmark' profile."""
import os

import pytest

from lab.models import DataOrigin, OpenAICompatAdapter, PROMPT_VERSION, advise, load_endpoints
from model_helpers import DEMO, ROOT, analysis, bench_profile  # noqa: F401

pytestmark = pytest.mark.live


@pytest.mark.skipif(os.environ.get("LAB_LIVE_LOCAL") != "1", reason="set LAB_LIVE_LOCAL=1")
def test_live_lm_studio(analysis, profile):
    ep = load_endpoints(ROOT / "configs" / "models.yaml")["local_lmstudio"]
    res = advise(OpenAICompatAdapter(ep, profile, prompt_version=PROMPT_VERSION), analysis, profile, run_id="live-local",
                 data_origin=DataOrigin.SYNTHETIC_DEMO)
    print(res.run_status, res.failure_kind, res.error_details, res.metrics)
    assert res.metrics.latency_ms is not None  # validity is reported, not required: small models often fail the schema


@pytest.mark.skipif(os.environ.get("LAB_LIVE_CLOUD") != "1" or not os.environ.get("CLOUD_MODEL_API_KEY"),
                    reason="set LAB_LIVE_CLOUD=1 and CLOUD_MODEL_API_KEY")
def test_live_cloud(analysis, bench_profile):
    ep = load_endpoints(ROOT / "configs" / "models.yaml")["cloud_default"]
    res = advise(OpenAICompatAdapter(ep, bench_profile, prompt_version=PROMPT_VERSION), analysis, bench_profile,
                 run_id="live-cloud", data_origin=DataOrigin.SYNTHETIC_DEMO)
    print(res.run_status, res.failure_kind, res.error_details, res.metrics)
    assert res.metrics.latency_ms is not None
