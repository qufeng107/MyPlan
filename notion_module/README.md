# notion_module v2

This package now includes three layers:

1. `reader.py`
   - Reads Config / Topics / Tasks / Leave from Notion.
   - Normalizes rows into Python dataclasses.

2. `writer.py`
   - Writes back fields such as `Next Date`, `SyncToGoogle`, `GoogleEventId`, `LastSyncedAt`, `Status`, `Records`, and core task fields.
   - Supports clearing fields by passing explicit `None` to update methods that use sentinel-based kwargs.

3. `next_date.py`
   - Computes the next occurrence for each task.
   - Supports `Once`, `Daily`, `Weekly`, `Monthly`, `Weekdays`, and `Holidays`.
   - Can skip leave conflicts when `Leave.AffectsScheduling = true`.

## Run the snapshot demo

From project root:

```bash
python -m notion_module.my_plan_notion_module_demo
```

## Recalculate next dates (dry run)

```bash
python -m notion_module.recalculate_next_dates
```

## Recalculate and write back to Notion

```bash
python -m notion_module.recalculate_next_dates --commit
```

## Optional holiday JSON

You can pass a holiday JSON file such as:

```json
["2026-01-01", "2026-04-03", "2026-04-06"]
```

Then run:

```bash
python -m notion_module.recalculate_next_dates --holidays-json holidays_uk.json
```
