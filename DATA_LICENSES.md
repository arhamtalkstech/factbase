# Data sources and terms

The repository ships **code, eval suites (questions and gold answers) and graded results**. It does not ship the raw item
streams; the dataset builders download them from the public sources below. If you rebuild and redistribute the streams,
follow each source's terms.

| Dataset | Source | Terms | What this repository contains |
|---|---|---|---|
| `markets` | FRED, Federal Reserve Bank of St. Louis (EIA oil prices, Treasury yields, FX, fed funds target; S&P 500, NASDAQ Composite, VIX) | FRED terms of use. Most series are public domain. **S&P 500 (S&P Dow Jones Indices), NASDAQ Composite (Nasdaq) and VIX (Cboe) are copyrighted by their owners**; FRED allows viewing but restricts redistribution of those series. | Questions with individual values as gold answers. No series data. |
| `football` | openfootball/football.json | CC0 1.0 (public domain) | Questions and results |
| `sec_filings` | SEC EDGAR XBRL company facts and submissions | US government public data | Questions and results |
| `fedreg` | Federal Register API | US government works, public domain | Questions and results |
| `world_quiz` | Stream: Wikipedia Current Events Portal (CC BY-SA 4.0). Quiz: RealTimeQA weekly news quizzes | RealTimeQA's repository declares no licence | **No question text.** Results keep ids, categories, verdicts and costs only. Rebuild locally with the builder. |
| `iran_headlines` | Stream: GDELT GKG 2.0 headlines. Quiz: written from Wikipedia Current Events Portal bullets | GDELT: free use with attribution. Wikipedia: CC BY-SA 4.0 | Questions (derived from Wikipedia text, so CC BY-SA 4.0) and results |
| `quakes` | USGS Earthquake Hazards Program FDSN event API | US government public domain | Questions and results |
| `weather` | Open-Meteo historical weather API (ERA5 reanalysis) | CC BY 4.0, attribution to Open-Meteo | Questions and results |
| `combined` | All of the above in one stream | As above | Questions except world_quiz rows |
| LongMemEval-S | xiaowu0162/longmemeval-cleaned (Hugging Face) | MIT | Results, which include the benchmark's questions and answers (MIT notice applies). The judge prompts in `factbase/eval/longmemeval.py` are taken from the benchmark's evaluation script (MIT). |

Attribution: Wikipedia contributors (Portal:Current events); the GDELT Project; USGS; Open-Meteo.com (CC BY 4.0); FRED,
Federal Reserve Bank of St. Louis; U.S. Securities and Exchange Commission; Office of the Federal Register; openfootball;
the LongMemEval authors (MIT).
