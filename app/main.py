"""FastAPI application: dashboard, review actions, CSV export, admin, webhook,
health — plus the APScheduler collection loop. Single-service deployment.
"""
from __future__ import annotations

import hmac
import io
import logging
import secrets
from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import Depends, FastAPI, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates

from .classifier import Classifier
from .collector import collect_once
from .config import get_settings
from .crud import delete_product, get_product, list_products, seed_from_file, upsert_product
from .db import SessionLocal, init_db
from .digest import build_digest
from .follow_watch import run_daily_watch
from .export import build_csv
from .models import Evidence, Product
from .pipeline import process_tweet
from .charts import assign_colors, build_line_chart, build_sentiment_bars
from .queries import EvidenceFilter, query_evidence
from .stats import build_overview
from .xclient import _map_tweet

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("gtm")

settings = get_settings()
templates = Jinja2Templates(directory="app/templates")
security = HTTPBasic()

CATEGORIES = ["demo", "customer_case", "expert_review", "partnership", "news", "promo", "irrelevant"]
SENTIMENTS = ["positive", "neutral", "negative"]
REVIEW_STATES = ["pending", "approved", "rejected"]
CATEGORY_LABELS = {
    "demo": "真实Demo", "customer_case": "客户Case", "expert_review": "大佬评价",
    "partnership": "合作/集成", "news": "资讯", "promo": "推广",
    "irrelevant": "无关", None: "未分类",
}

scheduler = BackgroundScheduler(timezone="UTC")


def _run_collection():
    try:
        stats = collect_once()
        log.info("Scheduled collection stats: %s", stats)
    except Exception:
        log.exception("Scheduled collection cycle crashed (will retry next interval)")


def _run_daily_watch():
    try:
        stats = run_daily_watch()
        log.info("Daily lab-watch stats: %s", stats)
    except Exception:
        log.exception("Daily lab-watch crashed (will retry tomorrow)")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    if settings.seed_products_file:
        s = SessionLocal()
        try:
            seed_from_file(s, settings.seed_products_file)
        except Exception:
            log.exception("Seeding failed (non-fatal)")
        finally:
            s.close()
    scheduler.add_job(
        _run_collection,
        "interval",
        minutes=settings.collect_interval_minutes,
        id="collect",
        next_run_time=None,  # first run after one interval; call /debug/collect to run now
        max_instances=1,
        coalesce=True,
    )
    if settings.follow_watch_enabled:
        scheduler.add_job(
            _run_daily_watch,
            "cron",
            hour=settings.follow_watch_hour_utc,
            id="daily_watch",
            max_instances=1,
            coalesce=True,
        )
        log.info("Daily lab-watch scheduled for %02d:00 UTC", settings.follow_watch_hour_utc)
    scheduler.start()
    log.info("Scheduler started: collecting every %d min", settings.collect_interval_minutes)
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="GTM Evidence Radar", lifespan=lifespan)


# --------------------------------------------------------------------------
# Auth
# --------------------------------------------------------------------------
def require_auth(credentials: HTTPBasicCredentials = Depends(security)):
    ok_user = secrets.compare_digest(credentials.username, settings.dashboard_user)
    ok_pass = secrets.compare_digest(credentials.password, settings.dashboard_password)
    if not (ok_user and ok_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --------------------------------------------------------------------------
# Health & debug
# --------------------------------------------------------------------------
@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/debug/collect")
def debug_collect(_: str = Depends(require_auth)):
    """Manually trigger one collection cycle (handy right after deploy)."""
    return collect_once()


@app.post("/debug/reset")
def debug_reset(_: str = Depends(require_auth), db=Depends(get_db)):
    """Purge all collected evidence and reset per-product watermarks for a clean
    re-pull under new collection rules. Keeps product config, the alert ledger
    (so a re-pull doesn't re-spam Feishu), and follow snapshots."""
    n = db.query(Evidence).delete()
    db.query(Product).update({Product.last_seen_tweet_id: None})
    db.commit()
    return {"deleted_evidence": n, "watermarks_reset": True}


@app.post("/debug/follow-watch")
def debug_follow_watch(_: str = Depends(require_auth)):
    """Manually trigger the daily lab-watch (new official posts + new follows).
    Also lets an external cron drive it if the app is ever scaled to >1 instance
    (in-process APScheduler would otherwise double-run)."""
    return run_daily_watch()


# --------------------------------------------------------------------------
# Overview dashboard (/)
# --------------------------------------------------------------------------
def _humanize(n: int) -> str:
    """Compact reach figure — 1.2M rather than 1,203,455, which is noise at
    stat-tile size."""
    for limit, suffix in ((1_000_000_000, "B"), (1_000_000, "M"), (1_000, "K")):
        if n >= limit:
            v = n / limit
            return f"{v:.1f}".rstrip("0").rstrip(".") + suffix
    return str(n)


@app.get("/", response_class=HTMLResponse)
def overview(request: Request, _: str = Depends(require_auth), db=Depends(get_db)):
    params = request.query_params
    try:
        days = min(max(int(params.get("days") or 14), 1), 365)
    except ValueError:
        days = 14
    try:
        product_id = int(params.get("product_id")) if params.get("product_id") else None
    except ValueError:
        product_id = None

    o = build_overview(db, product_id=product_id, days=days)
    colors = assign_colors(list(o.series.keys()))
    chart = build_line_chart(o.days, o.series)

    cat_totals = {c: sum(v.values()) for c, v in o.by_category.items()}
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "active": "overview",
            "o": o,
            "days": days,
            "colors": colors,
            "chart": chart,
            "sentiment_rows": build_sentiment_bars(o.by_sentiment, list(o.series.keys())),
            "cat_totals": cat_totals,
            "cat_max": max(cat_totals.values()) if cat_totals else 1,
            "category_order": CATEGORIES + ["unclassified"],
            "category_labels": {**CATEGORY_LABELS, "unclassified": "未分类"},
            "reach_h": _humanize(o.reach),
            "filters": params,
        },
    )


# --------------------------------------------------------------------------
# Weekly digest (/digest) — the narrative the GTM team opens each week
# --------------------------------------------------------------------------
@app.get("/digest", response_class=HTMLResponse)
def digest(request: Request, _: str = Depends(require_auth), db=Depends(get_db)):
    try:
        days = min(max(int(request.query_params.get("days") or 7), 1), 90)
    except ValueError:
        days = 7
    dg = build_digest(db, days=days)
    return templates.TemplateResponse(
        "digest.html",
        {
            "request": request,
            "active": "digest",
            "dg": dg,
            "category_labels": CATEGORY_LABELS,
        },
    )


# --------------------------------------------------------------------------
# Evidence feed (/feed) — the review queue
# --------------------------------------------------------------------------
@app.get("/feed", response_class=HTMLResponse)
def feed(request: Request, _: str = Depends(require_auth), db=Depends(get_db)):
    f = EvidenceFilter.from_query(request.query_params)
    items = query_evidence(db, f)
    products = list_products(db)
    return templates.TemplateResponse(
        "feed.html",
        {
            "request": request,
            "active": "feed",
            "items": items,
            "products": products,
            "categories": CATEGORIES,
            "sentiments": SENTIMENTS,
            "review_states": REVIEW_STATES,
            "category_labels": CATEGORY_LABELS,
            "filters": request.query_params,
            "qs": request.url.query,
        },
    )


@app.post("/evidence/{evidence_id}/review")
def review(evidence_id: int, action: str = Form(...), qs: str = Form(""),
           _: str = Depends(require_auth), db=Depends(get_db)):
    ev = db.get(Evidence, evidence_id)
    if ev is None:
        raise HTTPException(404, "evidence not found")
    if action in ("approve", "approved"):
        ev.review_status = "approved"
    elif action in ("reject", "rejected"):
        ev.review_status = "rejected"
    else:
        raise HTTPException(400, "invalid action")
    db.commit()
    return RedirectResponse(f"/feed?{qs}", status_code=303)


# --------------------------------------------------------------------------
# CSV export (/export) — the deliverable for the marketing team
# --------------------------------------------------------------------------
@app.get("/export")
def export_csv(request: Request, _: str = Depends(require_auth), db=Depends(get_db)):
    f = EvidenceFilter.from_query(request.query_params)
    f.limit = 2000
    items = query_evidence(db, f)
    data = build_csv(items)
    return StreamingResponse(
        io.BytesIO(data.encode("utf-8")),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=gtm_evidence.csv"},
    )


# --------------------------------------------------------------------------
# Admin: product config (/admin/products)
# --------------------------------------------------------------------------
@app.get("/admin/products", response_class=HTMLResponse)
def admin_products(request: Request, _: str = Depends(require_auth), db=Depends(get_db)):
    products = list_products(db)
    return templates.TemplateResponse(
        "admin_products.html",
        {"request": request, "active": "products", "products": products},
    )


def _split_lines(text: str) -> list[str]:
    """Accept newline- or comma-separated lists from the textarea."""
    if not text:
        return []
    parts = []
    for chunk in text.replace(",", "\n").splitlines():
        c = chunk.strip().lstrip("@")
        if c:
            parts.append(c)
    return parts


@app.post("/admin/products")
def admin_save(
    name: str = Form(...),
    keywords: str = Form(""),
    official_accounts: str = Form(""),
    seed_kols: str = Form(""),
    launch_date: str = Form(""),
    active: str = Form("on"),
    _: str = Depends(require_auth),
    db=Depends(get_db),
):
    upsert_product(db, {
        "name": name,
        "keywords": _split_lines(keywords),
        "official_accounts": _split_lines(official_accounts),
        "seed_kols": _split_lines(seed_kols),
        "launch_date": launch_date or None,
        "active": active in ("on", "true", "1", "yes"),
    })
    return RedirectResponse("/admin/products", status_code=303)


@app.post("/admin/products/{product_id}/delete")
def admin_delete(product_id: int, _: str = Depends(require_auth), db=Depends(get_db)):
    delete_product(db, product_id)
    return RedirectResponse("/admin/products", status_code=303)


# --------------------------------------------------------------------------
# Reserved webhook (/webhook/tweets) — shares the pipeline with polling.
# --------------------------------------------------------------------------
@app.post("/webhook/tweets")
async def webhook_tweets(request: Request, db=Depends(get_db)):
    # Shared-secret check (constant-time). twitterapi.io filter-rule webhooks
    # deliver a batch of tweets; we normalize + funnel each through the pipeline.
    provided = request.headers.get("X-Webhook-Secret", "")
    if not settings.webhook_secret or not hmac.compare_digest(provided, settings.webhook_secret):
        raise HTTPException(401, "bad webhook secret")

    payload = await request.json()
    raw_tweets = payload.get("tweets") or payload.get("data") or []
    # A webhook payload should indicate which product it maps to. We accept an
    # explicit product_id/product_name, else fall back to the first active one.
    products = list_products(db, only_active=True)
    by_name = {p.name.lower(): p for p in products}
    target = None
    if payload.get("product_id"):
        target = get_product(db, int(payload["product_id"]))
    elif payload.get("product_name"):
        target = by_name.get(str(payload["product_name"]).lower())
    if target is None:
        target = products[0] if products else None
    if target is None:
        raise HTTPException(400, "no active product to attribute webhook tweets to")

    classifier = Classifier()
    processed = 0
    for raw in raw_tweets:
        try:
            if process_tweet(db, target, _map_tweet(raw), classifier) is not None:
                processed += 1
        except Exception:
            log.exception("Webhook tweet processing failed (continuing)")
    return {"received": len(raw_tweets), "processed": processed, "product": target.name}
