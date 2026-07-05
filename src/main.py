"""
SAHPRA Watcher — Apify Actor Main Module

Entry point for the Apify Actor.  Orchestrates scraping, change detection,
dataset output, and pay-per-event charging.
"""

from apify import Actor

from .scraper import SOURCES, DETECTED_DATE, scrape_all


async def main() -> None:
    """Main Actor entrypoint."""
    async with Actor:
        Actor.log.info("SAHPRA Watcher Actor starting")

        # ── Read input ──
        actor_input = await Actor.get_input() or {}
        sources = actor_input.get("sources") or [s["id"] for s in SOURCES]
        max_items = actor_input.get("max_items", 25)

        Actor.log.info("Sources to scrape: %s", sources)
        Actor.log.info("Max items per source: %d", max_items)

        # ── Scrape ──
        new_items = await scrape_all(
            sources_to_scrape=sources,
            max_items=max_items,
        )

        total_new = len(new_items)
        Actor.log.info("Total new/changed items across all sources: %d", total_new)

        if total_new == 0:
            Actor.log.info("No changes detected — nothing to output.")
            await Actor.set_value("OUTPUT", {
                "status": "no_changes",
                "message": "No new or changed items detected.",
                "new_item_count": 0,
                "detected_at": DETECTED_DATE,
            })
            Actor.log.info("Run complete — zero items, no charges applied.")
            return

        # ── Push to dataset (with PPE charging) ──
        for item in new_items:
            await Actor.push_data(item, event_name="alert-item")

        Actor.log.info("Pushed %d items to dataset with pay-per-event charges", total_new)

        # ── Summary output ──
        await Actor.set_value("OUTPUT", {
            "status": "success",
            "new_item_count": total_new,
            "sources_checked": list(sources),
            "detected_at": DETECTED_DATE,
            "summary": f"Found {total_new} new or changed regulatory items from SAHPRA.",
        })

        Actor.log.info("SAHPRA Watcher run complete — %d items published", total_new)
