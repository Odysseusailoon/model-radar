"""Contract tests for bounded collection, attribution, recovery and agent access."""
from datetime import datetime, timezone
from unittest.mock import Mock

import httpx
import pytest

from app.xclient import Author, Tweet, XDataClient
from radar.catalog import Catalog, Entity, load_catalog
from radar.engine import scan
from radar.report import csv_export, markdown
from radar.schema import Budget, BudgetExceeded, ScanOptions
from radar.sources import Page, Sources, jobs_for
from radar.store import ScanBusy, Store


def entity(id="sglang", **extra):
    return Entity(id=id, name=id.title(), group="engine", website="https://example.com",
                  x_query=f'"{id}"', **extra)


def options(**extra):
    return ScanOptions(since="2026-11-01", until="2026-11-08", **extra)


def sample(e=None, source_id="123"):
    return Sources._signal(e or entity(), "x", source_id, "Test evidence", "A statement, not a verified result",
                           f"https://x.com/i/status/{source_id}", "2026-11-03T00:00:00Z",
                           "social_mention", "unverified_social_post", {})


def test_catalog_includes_requested_entities_and_disambiguates_generic_names():
    cat = load_catalog()
    ids = {e.id for e in cat.entities}
    assert {"sglang", "baseten", "fireworks", "modal", "together", "coreweave", "lambda", "nebius", "olmo", "llama"} <= ids
    assert all(e.reference_urls for e in cat.entities)
    assert cat.select(["modal"])[0].x_query != "Modal"
    with pytest.raises(ValueError):
        cat.select(["typo"])
    with pytest.raises(ValueError):
        Catalog(entities=[entity(), entity()])


def test_global_watchlist_keeps_official_labs_and_chinese_models_distinct():
    cat = load_catalog()
    by_id = {e.id: e for e in cat.entities}
    assert len(by_id) == 41
    assert {"reflection", "thinking-machines", "recursive", "ifm", "arcee", "zyphra", "muse", "nemotron", "olmo"} <= set(by_id)
    assert {e.id for e in cat.select(groups=["cn_models"])} == {
        "deepseek", "qwen", "kimi", "glm", "minimax", "yi", "stepfun", "internlm", "baichuan", "hunyuan", "ernie", "seed"}
    assert by_id["ifm"].hf_author == "IFM" and by_id["kimi"].hf_author == "moonshotai"
    assert "Silicon Valley" in by_id["ifm"].region_note
    assert by_id["muse"].hf_author == "meta-models"
    assert by_id["reflection"].hf_author == "reflection"
    assert by_id["thinking-machines"].hf_author == "thinkingmachines"
    assert by_id["recursive"].hf_author == "RecursiveSI"
    assert {"molmo", "olmo", "tulu"} <= set(by_id["olmo"].hf_families)
    jobs = jobs_for(cat.select(groups=["cn_models"]), options(sources=["huggingface"]))
    assert len(jobs) == 12
    assert options().max_requests >= len(jobs_for(cat.entities, options()))


@pytest.mark.parametrize("kwargs", [{"max_requests": 0}, {"max_pages": 11}, {"sources": []}])
def test_invalid_budget_is_rejected(kwargs):
    with pytest.raises(ValueError):
        options(**kwargs)


def test_window_and_plan_are_explicit():
    e = entity(github_repos=["sgl-project/sglang"])
    plan = jobs_for([e], options())
    assert "since:2026-11-01_00:00:00_UTC" in plan[0]["query"]
    assert "until:2026-11-08_00:00:00_UTC" in plan[0]["query"]
    assert len(plan) == 2
    with pytest.raises(ValueError):
        ScanOptions(since="2026-11-08", until="2026-11-01")


def test_x_page_boundary_cap_and_metadata():
    x = Mock()
    x.search_page.return_value = ([
        Tweet(id="1", text="in range", created_at=datetime(2026, 11, 3, tzinfo=timezone.utc)),
        Tweet(id="2", text="end excluded", created_at=datetime(2026, 11, 8, tzinfo=timezone.utc)),
        Tweet(id="3", text="undated"),
    ], "next", True)
    s = Sources(Budget(1), x_key="fixture", x_client=x)
    try:
        pages = list(s.pages(entity(), jobs_for([entity()], options())[0], options()))
    finally:
        s.close()
    assert [r.source_id for r in pages[0].signals] == ["1"]
    assert pages[0].has_more and pages[0].invalid_records == 1
    assert x.search_page.call_count == 1


def test_budget_counts_x_retries(monkeypatch):
    calls = []
    def get(url, **kwargs):
        calls.append(url)
        return httpx.Response(429, request=httpx.Request("GET", url))
    monkeypatch.setattr("app.xclient.httpx.get", get)
    monkeypatch.setattr("app.xclient.time.sleep", lambda _: None)
    budget = Budget(2)
    x = XDataClient("fixture", min_interval=0, before_request=budget.consume)
    with pytest.raises(BudgetExceeded):
        x.search_page("test")
    assert len(calls) == budget.used == 2


def test_x_error_envelope_does_not_look_like_zero_results(monkeypatch):
    x = XDataClient("fixture")
    monkeypatch.setattr(x, "_get", lambda *a: {"status": "error", "message": "bad key"})
    with pytest.raises(ValueError):
        x.search_page("test")


def test_github_excludes_drafts_and_keeps_prerelease_and_coverage():
    def handler(request):
        assert request.url.params["per_page"] == "50"
        return httpx.Response(200, json=[
            {"id": 1, "tag_name": "v1", "name": "Release", "published_at": "2026-11-03T00:00:00Z"},
            {"id": 2, "tag_name": "v2", "published_at": "2026-11-04T00:00:00Z", "prerelease": True},
            {"id": 3, "tag_name": "draft", "draft": True},
        ], headers={"Link": '<https://api.github.com/repos/sgl-project/sglang/releases?page=2>; rel="next"'})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        e = entity(github_repos=["sgl-project/sglang"])
        opts = options(sources=["github"])
        pages = list(Sources(Budget(1), client=client).pages(e, jobs_for([e], opts)[0], opts))
    assert [s.event_kind for s in pages[0].signals] == ["software_release", "prerelease"]
    assert pages[0].has_more


def test_hf_retains_license_and_does_not_call_metadata_edit_a_release():
    def handler(request):
        return httpx.Response(200, json=[
            {"id": "google/gemma-test", "sha": "abc", "lastModified": "2026-11-03T00:00:00Z",
             "cardData": {"license": "gemma"}, "gated": "manual", "siblings": [{"rfilename": "weights.safetensors"}]},
            {"id": "google/bert", "lastModified": "2026-11-04T00:00:00Z"},
            {"id": "someone/gemma-test", "lastModified": "2026-11-04T00:00:00Z"},
        ])
    e = entity(hf_author="google", hf_families=["gemma"])
    opts = options(sources=["huggingface"])
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        pages = list(Sources(Budget(1), client=client).pages(e, jobs_for([e], opts)[0], opts))
    assert len(pages[0].signals) == 1
    row = pages[0].signals[0]
    assert row.event_kind == "model_repository_update"
    assert row.metadata["license"] == "gemma" and row.metadata["gated"] == "manual"
    assert row.metadata["weight_files_listed"] is True
    assert row.metadata["license_verified"] is False


def test_hf_pagination_cannot_redirect_to_another_host():
    def handler(request):
        return httpx.Response(200, json=[], headers={"Link": '<https://evil.example/api/models>; rel="next"'})
    e = entity(hf_author="google")
    opts = options(sources=["huggingface"], max_pages=2)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match="invalid_pagination"):
            list(Sources(Budget(2), client=client).pages(e, jobs_for([e], opts)[0], opts))


def test_cross_entity_dedup_and_resume_only_retries_failed_sources(tmp_path):
    cat = Catalog(entities=[entity("first"), entity("second")])
    calls = []
    fail = True
    class FakeSources:
        def __init__(self, budget, **kwargs): self.budget = budget
        def close(self): pass
        def pages(self, e, job, opts):
            self.budget.consume()
            calls.append(e.id)
            if e.id == "second" and fail:
                raise RuntimeError("credential-that-must-not-leak")
            yield Page([sample(e)])
    store = Store(tmp_path)
    first = scan(cat, cat.entities, options(sources=["x"]), store, x_key="fixture", sources_factory=FakeSources)
    assert first["status"] == "partial"
    assert "credential-that-must-not-leak" not in str(first)
    fail = False
    second = scan(cat, cat.entities, options(), store, x_key="fixture", resume=first["id"], sources_factory=FakeSources)
    assert calls == ["first", "second", "second"]
    assert second["status"] == "complete"
    assert len(second["signals"]) == 1
    assert second["signals"][0]["entity_ids"] == ["first", "second"]
    assert second["requests_used"] == 3


def test_missing_key_and_budget_exhaustion_are_visible(tmp_path):
    e = entity(github_repos=["sgl-project/sglang"])
    cat = Catalog(entities=[e])
    class FakeSources:
        def __init__(self, budget, **kwargs): pass
        def close(self): pass
        def pages(self, *args): raise BudgetExceeded()
    run = scan(cat, [e], options(), Store(tmp_path), sources_factory=FakeSources)
    assert run["status"] == "failed"
    assert [c["error"] for c in run["coverage"]] == ["missing_twitterapi_key", "request_budget_exhausted"]


def test_page_cap_is_partial_and_resume_does_not_repeat_paid_queries(tmp_path):
    cat = Catalog(entities=[entity()])
    calls = []
    class FakeSources:
        def __init__(self, budget, **kwargs): pass
        def close(self): pass
        def pages(self, e, *args):
            calls.append(e.id)
            yield Page([sample(e)], has_more=True)
    store = Store(tmp_path)
    run = scan(cat, cat.entities, options(), store, x_key="fixture", sources_factory=FakeSources)
    scan(cat, cat.entities, options(), store, x_key="fixture", resume=run["id"], sources_factory=FakeSources)
    assert run["status"] == "partial" and len(calls) == 1
    assert "page cap reached" in markdown(run)


def test_interrupted_source_keeps_already_returned_evidence(tmp_path):
    cat = Catalog(entities=[entity()])
    class FakeSources:
        def __init__(self, budget, **kwargs): pass
        def close(self): pass
        def pages(self, e, *args):
            yield Page([sample(e)], has_more=True)
            raise httpx.ReadTimeout("private request detail")
    run = scan(cat, cat.entities, options(max_pages=2), Store(tmp_path), x_key="fixture", sources_factory=FakeSources)
    assert len(run["signals"]) == 1
    assert run["coverage"][0]["error"] == "ReadTimeout"
    assert "private request detail" not in markdown(run)


def test_store_rejects_paths_and_concurrent_collectors(tmp_path):
    store = Store(tmp_path)
    with pytest.raises(ValueError):
        store.get("../../.env")
    with store.lock():
        with pytest.raises(ScanBusy):
            with Store(tmp_path).lock():
                pass


def test_cli_plan_never_requires_network_or_credentials(tmp_path, capsys):
    from radar.__main__ import main
    assert main(["--data-dir", str(tmp_path), "plan", "--entities", "sglang", "--sources", "github"]) == 0
    assert '"sgl-project/sglang"' in capsys.readouterr().out
    assert not list(tmp_path.iterdir())


def test_read_only_api_and_dashboard(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "inference_radar_data_dir", str(tmp_path))
    monkeypatch.setattr(settings, "radar_read_token", "fixture-reader")
    with TestClient(app) as c:
        assert c.get("/api/radar/catalog").status_code == 401
        assert c.get("/inference").status_code == 401
        headers = {"Authorization": "Bearer fixture-reader"}
        assert c.get("/api/radar/catalog", headers=headers).status_code == 200
        assert c.get("/api/radar/latest", headers=headers).status_code == 404
        assert c.post("/debug/inference-collect", headers=headers).status_code == 401
        response = c.get("/inference", auth=("smoke-user", "smoke-pass"))
        assert response.status_code == 200 and ">41</div>" in response.text and "Chinese open models" in response.text and "Not run yet" in response.text


def test_report_escapes_untrusted_content_and_csv_formulas():
    row = sample().model_dump()
    row["title"] = "=HYPERLINK(\"bad\")"
    row["text"] = "<script>alert(1)</script> [click](javascript:bad)"
    run = {"id": "a" * 32, "entities": [entity().model_dump()], "status": "partial",
           "options": options().model_dump(mode="json"), "signals": [row], "coverage": []}
    assert "<script>" not in markdown(run)
    assert "\\[click\\]" in markdown(run)
    assert "'=HYPERLINK" in csv_export(run)


def test_repeated_monitoring_marks_previously_seen_evidence(tmp_path):
    cat = Catalog(entities=[entity()])
    class FakeSources:
        def __init__(self, budget, **kwargs): pass
        def close(self): pass
        def pages(self, e, *args): yield Page([sample(e)])
    store = Store(tmp_path)
    first = scan(cat, cat.entities, options(), store, x_key="fixture", sources_factory=FakeSources)
    second = scan(cat, cat.entities, options(), store, x_key="fixture", sources_factory=FakeSources)
    assert first["signals"][0]["is_new"] is True
    assert second["signals"][0]["is_new"] is False
    assert first["signals"][0]["first_seen_at"] == second["signals"][0]["first_seen_at"]


def test_topic_hints_are_explicit_and_nonexclusive():
    from radar.topics import topic_tags
    tags = topic_tags("New H100 capacity: lower pricing and faster throughput")
    assert {"hardware_capacity", "pricing", "performance"} <= set(tags)
    assert topic_tags("a generic comment") == []
    assert "pricing" not in topic_tags("IPO valuation: $20 billion market cap")
    assert "pricing" in topic_tags("GPU costs have dropped by 20%")


def test_standalone_dashboard_has_no_postgres_startup_or_broken_gtm_links(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from radar.web import app
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "inference_radar_data_dir", str(tmp_path))
    with TestClient(app) as c:
        assert c.get("/health").status_code == 200
        r = c.get("/", auth=("smoke-user", "smoke-pass"))
        assert r.status_code == 200 and "Inference Radar" in r.text
        assert 'href="/feed"' not in r.text


def test_scheduler_is_opt_in_and_uses_shared_collector(monkeypatch):
    from app.config import get_settings
    from app.inference_radar import configure_radar_job, run_radar_once
    s = get_settings()
    scheduler = Mock()
    monkeypatch.setattr(s, "inference_radar_enabled", False)
    configure_radar_job(scheduler)
    scheduler.add_job.assert_not_called()
    monkeypatch.setattr(s, "inference_radar_enabled", True)
    configure_radar_job(scheduler)
    assert scheduler.add_job.call_args.args[0] == run_radar_once
    assert scheduler.add_job.call_args.kwargs["max_instances"] == 1
