# SAHPRA Regulatory Monitor — Apify Actor

Monitors the South African Health Products Regulatory Authority (SAHPRA) for safety alerts, drug recalls, regulatory changes, and public notices. Designed for pharma compliance, regulatory affairs, and competitive intelligence teams.

## Quick Start

1. **Run with defaults** — click "Run" and the actor checks all 6 SAHPRA pages
2. **First run** outputs all current items as "new" (acts as baseline)
3. **Subsequent runs** only output **new or changed** items (change detection via SHA256 hash)
4. **Get structured JSON** via Apify API — integrate into any compliance workflow

## Sources Monitored

| Source | URL | Category |
|--------|-----|----------|
| Safety Alerts | https://www.sahpra.org.za/safety-alerts/ | Safety signals, drug interactions |
| Product Recalls | https://www.sahpra.org.za/product-recalls/ | Recall notices |
| Latest News | https://www.sahpra.org.za/latest-news-updates/ | Regulatory updates |
| Communication to Industry | https://www.sahpra.org.za/communication-to-industry/ | Industry guidance |
| Documents for Comments | https://www.sahpra.org.za/documents-for-comments/ | Draft regulations (includes deadlines) |
| Safety Information | https://www.sahpra.org.za/safety-information-and-updates/ | Safety updates |

## Output Schema

Each alert item:

```json
{
  "source": "safety_alerts | product_recalls | news | industry_comm | documents_for_comment | safety_info",
  "title": "Warfarin and Tramadol – Harmful Drug-Drug Interaction",
  "url": "https://www.sahpra.org.za/safety-alerts/...",
  "published_date": "2025-06-06",
  "detected_date": "2026-07-04T14:00:00Z",
  "summary": "SAHPRA informs healthcare professionals...",
  "category": "safety_signal | recall | regulatory_change | public_comment",
  "products_affected": [],
  "is_new": true,
  "change_type": "new | update"
}
```

## Pricing

- **Pay-per-event:** $0.005 per alert item
- **Rental:** $19/month (includes daily scheduled runs)

## Safeguards

- Rate limiting (2-5s random jitter between requests)
- Retry with exponential backoff (3 retries, 1.5s/3s/6s)
- HTTP connection pooling (keep-alive, 8 max connections)
- SHA256 change detection (zero-cost empty runs for unchanged pages)
- Input validation (source selection constrained to enum, max_items capped 1-100)

## Who Is This For?

- **Pharma companies** — monitor competitor registration activity, recall alerts
- **Regulatory affairs teams** — get notified when SAHPRA opens public comment periods
- **Compliance officers** — track safety signals and medicine interactions
- **Generics manufacturers** — watch for regulatory changes affecting product pipelines

## Deployment

Deployed on Apify Cloud. Requires Apify account.

```bash
npm install -g apify-cli
apify login
apify push
```

## License

Proprietary — Medicaputare (Pty) Ltd
