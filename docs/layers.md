# Layered additions (v7)

`factbase/memories/layered.py` adds seven layers to the v6 design. Each is a constructor switch on `FactbaseV7`, so it
can be turned on or off per deployment and measured on its own (`factbase/memories/registry.py` defines the variants).
The evaluation is in [`v7_results.md`](v7_results.md).

| Switch | What it does | In the recommended configuration (`factbase_v7c`) |
|---|---|---|
| `extract_v2` | Every extracted fact also gets a topic label, a memory type and a priority, in the same single extraction call. | **on**: this alone moved LongMemEval-S test from 82.3% to 87.2% |
| `typed` | Fact search ranks by relevance first and lets priority lift a fact by up to four places. Nothing is dropped for low priority. | off (no measurable effect) |
| `profile` | A standing profile of the person, rebuilt from current preference / instruction / state / plan facts whenever about 30 new ones arrive. It is always rebuilt from facts, never from its own previous text, so errors cannot compound. Every bullet cites fact ids. It sits in the stable part of the prompt, so it is cached across questions. | off for accuracy (no measurable effect); on when a readable profile is wanted |
| `conflicts` | Non-destructive conflict resolution. Each new state-like fact is compared with similar earlier facts (embedding similarity of at least 0.72, plus earlier facts with the same subject and attribute). An LLM marks it `duplicate`, `updates` or `contradicts`. Replaced facts become `superseded` with a `valid_to` date, duplicates are hidden from search, contradictions are flagged `DISPUTED`; nothing is deleted. Every decision is logged in the `relations` table. | off for accuracy; on when an audit log of changes is wanted |
| `threads` | Topic labels are merged in time order into persistent threads (label embedding similarity of at least 0.75). Tools `list_threads` and `get_thread`; the most relevant threads are listed in the initial context. | off (hurt on the dev split; no gain on interleaved channels) |
| `offload` | Reversible offload of the agent's working memory. Tool outputs older than the last round become one-line stubs; `open_ref` restores the full text. | off (raised cost by breaking the prompt cache; useful only for much longer agent sessions) |
| `budget` | Maximum number of search calls per question (default 6). | on (rarely binding; caps the worst case) |

Always present in v7:

- `read_records(ids)`: exact raw records by id, so any fact, thread or profile bullet can be traced back to its evidence.
- `export_views(dir)`: writes the derived layers as Markdown (`index.md`, `profile.md`, `threads/<id>.md`), each line
  keeping its fact and source ids, for human review.
- The initial context is assembled within a time budget (`context_budget_s`), so a slow optional layer never delays an answer.

## Data structures added

```sql
ALTER TABLE facts ADD COLUMN topic TEXT;         -- label from extraction
ALTER TABLE facts ADD COLUMN mem_type TEXT;      -- preference | instruction | plan | state | event
ALTER TABLE facts ADD COLUMN priority INTEGER;   -- 0-100, ranking only
ALTER TABLE facts ADD COLUMN thread_id TEXT;     -- persistent thread
ALTER TABLE facts ADD COLUMN duplicate_of TEXT;  -- set by conflict resolution
ALTER TABLE facts ADD COLUMN relation TEXT;      -- duplicate | updated | disputed
CREATE TABLE threads (thread_id TEXT PRIMARY KEY, label TEXT, feed TEXT, first_date TEXT, last_date TEXT, n_facts INTEGER);
CREATE TABLE relations (fact_id TEXT, other_id TEXT, relation TEXT, decided_at TEXT);  -- audit log of every decision
```

The profile is held in memory as text plus a build counter. Thread labels are held as an embedding matrix for merging.

## Configurations

| Name | Use for | Layers | Measured |
|---|---|---|---|
| `factbase_v7c` | Conversations | v6 conversation design + `extract_v2` | 87.2% LongMemEval-S test (v6u 82.3%) |
| `factbase_v7u_best` | Conversations, with audit views | + `profile`, `conflicts`, `typed` | 86.4% (pre-registered test result) |
| `agentic_sql_v6f` | Fact and market feeds | unchanged v6 design (no v7 layer helped on feeds) | 96.4% sample, 93% held-out |
