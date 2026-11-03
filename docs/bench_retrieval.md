# Retrieval and SQL latency by corpus size

Median / p95 in milliseconds, single thread on an 18-core Apple Silicon laptop, brute-force vectors (no ANN), SQLite FTS5. Rows beyond 339,210 are synthetic copies of real headlines.

| rows | dense f32 | dense f16 | BM25 top-100 | SQL count by date | SQL date + LIKE | SQL full-table LIKE |
|---|---|---|---|---|---|---|
| 10,000 | 0.1 / 0.1 | 3.5 / 3.5 | 0.4 / 2.1 | 0.0 / 0.0 | 0.0 / 0.0 | 1.0 / 1.0 |
| 100,000 | 1.4 / 1.7 | 35.0 / 35.2 | 3.9 / 20.7 | 0.0 / 0.0 | 0.0 / 0.0 | 10.5 / 10.5 |
| 339,210 | 5.0 / 5.9 | 118.7 / 121.7 | 17.3 / 76.8 | 0.6 / 0.7 | 7.5 / 7.6 | 34.9 / 34.9 |
| 1,000,000 | 15.8 / 17.7 | 351.8 / 363.6 | 55.4 / 228.9 | 2.1 / 2.2 | 22.9 / 23.7 | 106.8 / 106.8 |
| 3,000,000 | 44.4 / 49.5 | 1057.0 / 1073.6 | 164.4 / 706.2 | 6.3 / 6.4 | 69.1 / 69.2 | 312.7 / 312.7 |
