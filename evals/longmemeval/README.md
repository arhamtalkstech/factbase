# LongMemEval-S

Long multi-session chat histories: 500 questions, each with its own history of about 50 sessions (~120k tokens), most of
them unrelated filler. Question types: single-session (user, assistant, preference), multi-session aggregation, knowledge
update, temporal reasoning, and 30 unanswerable questions.

Not redistributed here. Download (MIT licence):

```bash
mkdir -p data/raw/longmemeval
curl -L -o data/raw/longmemeval/longmemeval_s_cleaned.json \
  https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned/resolve/main/longmemeval_s_cleaned.json
```

How it is used (`factbase/eval/longmemeval.py`):

- Each question gets its own memory built from its own history: one item per round (a user turn plus the assistant
  reply), time-stamped with the session date, ingested in time order, then asked at the question date.
- **Fixed split:** a question is in `dev` if the SHA-1 of its id mod 5 is 0 (85 questions), else in `test` (415). All
  design choices were made on dev; test was run once per configuration.
- **Interleaved channel** (`--interleave`): all sessions held on the same day are mixed message by message into one
  channel with no session labels, each message keeping its true date. `--subset 120` takes a fixed stratified subset of
  20 questions per type.
- **Grading** uses the benchmark's official yes/no judge prompts with grok-4.3 as the judge model.
