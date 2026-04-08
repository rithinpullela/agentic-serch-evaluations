# Understanding the Results: A Complete Guide

This guide explains how to read and interpret all the data files in this repository.

## Table of Contents

- [Quick Reference](#quick-reference)
- [Raw Results Files](#raw-results-files)
- [Metrics Analysis File](#metrics-analysis-file)
- [LLM Judge Results](#llm-judge-results)
- [How to Use This Data](#how-to-use-this-data)
- [Common Questions](#common-questions)

---

## Quick Reference

### File Sizes and Purposes

| File | Size | Purpose | Key Fields |
|------|------|---------|------------|
| `results/*.json` | 291-526 KB | Raw query responses | hits, latency, DSL |
| `analysis/metrics_analysis.json` | 669 KB | Quantitative metrics | consistency, latency, errors |
| `analysis/llm_judging_input.json` | 600 KB | Prepared for evaluation | top_results, query |
| `analysis/llm_judgments_full_NEW.json` | 515 KB | Quality scores | overall_score, reasoning |

### What Each Metric Means

| Metric | Range | Good Value | Bad Value | What It Measures |
|--------|-------|------------|-----------|------------------|
| **Result Consistency** | 0-100% | >70% | <40% | How similar results are across runs |
| **Zero-Result Rate** | 0-100% | 0% | >10% | How often queries return nothing |
| **Avg Latency** | ms | <2000ms | >3000ms | Response time |
| **LLM Judge Score** | 1-5 | >4.0 | <3.0 | Overall quality |

---

## Raw Results Files

Location: `results/*.json`

Each file contains 50 query executions (5 queries × 10 runs) for one approach.

### Structure

```json
{
  "pipeline": "tools_v1_pipe",
  "timestamp": "2026-04-07T17:16:23.123456",
  "num_runs": 10,
  "queries": [
    {
      "query_text": "Find summer dresses for my wife's birthday party under $60",
      "runs": [
        {
          "run_number": 1,
          "timestamp": "2026-04-07T17:16:25.456789",
          "success": true,
          "server_latency_ms": 2047,
          "client_latency_ms": 2150,
          "total_hits": 168,
          "dsl_query": "{...}",
          "hits": [
            {
              "_id": "12345",
              "_score": 1.0,
              "_source": {
                "productDisplayName": "Women Blue Dress",
                "price": 45.99,
                "gender": "Women",
                "masterCategory": "Apparel",
                "articleType": "Dresses",
                "baseColour": "Blue",
                "season": "Summer",
                "usage": "Party",
                "avgRating": 4.2,
                "numRatings": 156
              }
            },
            // ... 9 more products (top 10)
          ]
        },
        // ... 9 more runs
      ]
    },
    // ... 4 more queries
  ]
}
```

### Key Fields Explained

#### Top Level
- **`pipeline`**: Which approach was tested (tools_v1_pipe, templates_pipe, normal_pipe, sonnet_pipe)
- **`timestamp`**: When experiment started
- **`num_runs`**: How many times each query was executed (always 10)

#### Query Level
- **`query_text`**: The natural language question asked
- **`runs`**: Array of 10 executions of this query

#### Run Level
- **`run_number`**: Which execution (1-10)
- **`success`**: Did the query execute without errors? (true/false)
- **`server_latency_ms`**: OpenSearch processing time (LLM + query execution)
- **`client_latency_ms`**: Total time including network (higher than server)
- **`total_hits`**: How many products matched the query
- **`dsl_query`**: The actual OpenSearch DSL query generated/executed
- **`hits`**: Top 10 products returned (array of documents)

#### Hit (Product) Level
- **`_id`**: Unique product identifier (used for consistency measurement)
- **`_score`**: Relevance score from OpenSearch
- **`_source`**: Product data (name, price, attributes, ratings)

### Example: Reading a Single Run

```json
{
  "run_number": 3,
  "success": true,
  "server_latency_ms": 2230,
  "total_hits": 168,
  "hits": [
    {
      "_id": "42567",
      "_source": {
        "productDisplayName": "Peter England Women Blue Dress",
        "price": 53.99,
        "gender": "Women"
      }
    }
  ]
}
```

**Interpretation:**
- This was the 3rd execution of the query
- Query succeeded without errors
- Took 2.23 seconds to process
- Found 168 matching products
- Top result: Blue dress for women at $53.99
- Product ID "42567" will be used to measure consistency across runs

### What to Look For

**Good Sign:**
- `success: true` across all runs
- `total_hits > 0` for all runs (no zero-results)
- Similar `total_hits` values across runs (stable)
- Same product IDs appearing in `hits` across runs (consistent)

**Red Flag:**
- `success: false` (query errors)
- `total_hits: 0` (zero-results - failure)
- Wildly different `total_hits` across runs (unstable)
- Completely different product IDs in `hits` (inconsistent)

---

## Metrics Analysis File

Location: `analysis/metrics_analysis.json`

Contains calculated metrics for all 4 pipelines.

### Structure

```json
{
  "tools_v1_pipe": {
    "pipeline": "tools_v1_pipe",
    "latency": { ... },
    "reproducibility": { ... },
    "errors": { ... },
    "llm_judging_data": [ ... ]
  },
  "templates_pipe": { ... },
  "normal_pipe": { ... },
  "sonnet_pipe": { ... }
}
```

### Latency Section

```json
"latency": {
  "mean": 2061.2,
  "median": 1979.0,
  "std_dev": 234.5,
  "min": 1523,
  "max": 2632,
  "p50": 1979,
  "p95": 2447,
  "p99": 2632,
  "per_query": {
    "Find summer dresses for my wife's birthday party unde...": {
      "mean": 2450.3,
      "median": 2398.0,
      "min": 2047,
      "max": 3489,
      "std_dev": 423.2
    }
  }
}
```

**What This Means:**

- **`mean: 2061.2`** - Average response time across all 50 runs: 2.06 seconds
- **`median: 1979.0`** - Middle value (50th percentile): 1.98 seconds
- **`p95: 2447`** - 95% of queries complete within 2.45 seconds
- **`p99: 2632`** - 99% complete within 2.63 seconds (worst-case)
- **`per_query`** - Breakdown by individual query (some queries naturally slower)

**How to Interpret:**
- Mean < 2000ms: Fast (good for real-time search)
- Mean 2000-3000ms: Acceptable but could be better
- Mean > 3000ms: Too slow for production

### Reproducibility Section

```json
"reproducibility": {
  "result_consistency": {
    "Find summer dresses for my wife's birthday party unde...": {
      "avg_jaccard_similarity": 0.731,
      "similarity_pct": 73.1
    }
  },
  "hit_count_stability": {
    "Find summer dresses for my wife's birthday party unde...": {
      "mean": 168.0,
      "std_dev": 0.0,
      "min": 168,
      "max": 168,
      "variance_pct": 0.0
    }
  },
  "dsl_consistency": {
    "Find summer dresses for my wife's birthday party unde...": {
      "unique_dsls": 4,
      "total_runs": 10,
      "consistency_pct": 60.0
    }
  },
  "overall_result_consistency_pct": 73.1,
  "overall_dsl_consistency_pct": 40.0
}
```

**What This Means:**

**Result Consistency (Most Important):**
- **`avg_jaccard_similarity: 0.731`** - 73.1% overlap in products across runs
- Calculated by comparing all 45 pairs of runs (10 choose 2)
- Higher = more predictable results

**Hit Count Stability:**
- **`mean: 168.0, std_dev: 0.0`** - Always returns exactly 168 products
- Variance 0% means perfectly stable count
- Shows query parameters extracted consistently

**DSL Consistency (Less Important):**
- **`unique_dsls: 4`** - Generated 4 different DSL queries across 10 runs
- **`consistency_pct: 60%`** - 60% of runs used the same DSL
- Lower DSL consistency OK if result consistency is high (different queries, same results)

**Overall Metrics:**
- **`overall_result_consistency_pct: 73.1`** - Average across all 5 queries
- This is the PRIMARY METRIC for comparison

**How to Interpret:**
- Result consistency >70%: Excellent (predictable, trustworthy)
- 50-70%: Acceptable (some variation but usable)
- <50%: Poor (unpredictable, feels random)

### Errors Section

```json
"errors": {
  "total_runs": 50,
  "successful_runs": 50,
  "failed_runs": 0,
  "success_rate_pct": 100.0,
  "error_rate_pct": 0.0,
  "timeout_runs": 0,
  "timeout_rate_pct": 0.0,
  "zero_result_runs": 0,
  "zero_result_rate_pct": 0.0,
  "errors_by_type": {},
  "per_query": {
    "Find summer dresses...": {
      "total": 10,
      "successful": 10,
      "success_rate_pct": 100.0,
      "zero_result_count": 0
    }
  }
}
```

**What This Means:**

- **`success_rate_pct: 100.0`** - All queries executed without errors
- **`zero_result_rate_pct: 0.0`** - No queries returned 0 hits (perfect reliability)
- **`timeout_rate_pct: 0.0`** - No timeouts occurred
- **`errors_by_type: {}`** - No errors of any type

**How to Interpret:**
- Zero-result rate 0%: Perfect (production-ready)
- Zero-result rate 1-5%: Acceptable (but investigate failures)
- Zero-result rate >10%: Unacceptable (blocks production use)

---

## LLM Judge Results

Location: `analysis/llm_judgments_full_NEW.json`

Contains quality evaluations from Claude Sonnet 4.6 for all 250 query results.

### Structure

```json
{
  "tools_v1_pipe": [
    {
      "query": "Find summer dresses for my wife's birthday party under $60",
      "run_number": 1,
      "judgment": {
        "relevance_analysis": {
          "q1_product_type_match": "Yes - All 10 results are dresses...",
          "q2_demographic_match": "Yes - All results are Women's dresses...",
          "q3_occasion_match": "Yes - Results include party-appropriate styles...",
          "relevance_score": 5
        },
        "precision_analysis": {
          "q1_price_constraints": "Yes - All products under $60...",
          "q2_attribute_constraints": "Yes - Summer season, party usage matched...",
          "q3_no_obvious_mismatches": "Yes - No mismatches found",
          "precision_score": 5
        },
        "quality_analysis": {
          "q1_variety": "Yes - Good variety in colors, brands, styles...",
          "q2_ratings": "Yes - Most products rated 4.0+ stars",
          "q3_selection_size": "Yes - 168 hits provides ample choice",
          "quality_score": 5
        },
        "completeness_analysis": {
          "q1_query_coverage": "Yes - Covers dresses, summer, party, price...",
          "q2_attribute_completeness": "Yes - All attributes present",
          "q3_inventory_representation": "Yes - Good coverage of available inventory",
          "completeness_score": 5
        },
        "overall_score": 5.0,
        "critical_issues": [],
        "suggestions": []
      }
    },
    // ... 49 more evaluations
  ],
  "templates_pipe": [ ... ],
  "normal_pipe": [ ... ],
  "sonnet_pipe": [ ... ]
}
```

### Key Fields Explained

**Per Evaluation:**
- **`query`**: Natural language question
- **`run_number`**: Which execution (1-10)
- **`judgment`**: LLM's structured evaluation

**Four Quality Dimensions:**

Each dimension follows this pattern:
1. Answer yes/no questions about specific criteria
2. Provide reasoning for each answer
3. Map answers to score (1-5)

**Relevance (Does it match intent?):**
- Q1: Correct product type?
- Q2: Target demographic matched?
- Q3: Occasion/usage appropriate?

**Precision (Satisfies constraints?):**
- Q1: Price limits respected?
- Q2: Attributes (color, season) matched?
- Q3: No obvious errors?

**Quality (Good recommendations?):**
- Q1: Variety in options?
- Q2: Acceptable ratings?
- Q3: Sufficient selection?

**Completeness (Covers query well?):**
- Q1: All query aspects addressed?
- Q2: Important attributes present?
- Q3: Inventory well-represented?

**Overall:**
- **`overall_score`**: Average of 4 dimension scores
- **`critical_issues`**: List of serious problems found
- **`suggestions`**: Improvement recommendations

### Example: Perfect Score

```json
{
  "relevance_score": 5,
  "precision_score": 5,
  "quality_score": 5,
  "completeness_score": 5,
  "overall_score": 5.0,
  "critical_issues": [],
  "suggestions": ["Could include more designer brands for premium segment"]
}
```

**Interpretation:** Excellent results. All criteria met. Only minor enhancement suggestion.

### Example: Poor Score

```json
{
  "relevance_score": 2,
  "precision_score": 1,
  "quality_score": 2,
  "completeness_score": 1,
  "overall_score": 1.5,
  "critical_issues": [
    "Results returned 0 products - complete failure",
    "Query over-constrained with too many filters"
  ],
  "suggestions": [
    "Implement graceful degradation for zero-results",
    "Relax optional filters when no matches found"
  ]
}
```

**Interpretation:** Failed query. Zero results returned. Critical issues identified. Needs architectural fix.

### Aggregating Scores

To get pipeline-level score:
```python
all_scores = [eval["judgment"]["overall_score"] for eval in pipeline_evals]
mean_score = sum(all_scores) / len(all_scores)
std_dev = stdev(all_scores)
```

**Tool-based:**
- Mean: 4.02/5
- Std Dev: 0.68 (consistent quality)

**Templates:**
- Mean: 3.04/5
- Std Dev: 0.75 (more variable)

**How to Interpret Overall Scores:**
- 4.5-5.0: Excellent (production-ready)
- 4.0-4.5: Good (minor improvements possible)
- 3.0-4.0: Acceptable (functional but issues exist)
- 2.0-3.0: Poor (significant problems)
- <2.0: Failed (not usable)

---

## How to Use This Data

### Compare Pipelines

**Quick comparison script:**
```python
import json

# Load metrics
with open('analysis/metrics_analysis.json') as f:
    metrics = json.load(f)

# Compare key metrics
pipelines = ['tools_v1_pipe', 'templates_pipe', 'normal_pipe', 'sonnet_pipe']
for pipeline in pipelines:
    p = metrics[pipeline]
    print(f"\n{pipeline}:")
    print(f"  Consistency: {p['reproducibility']['overall_result_consistency_pct']:.1f}%")
    print(f"  Zero-Results: {p['errors']['zero_result_rate_pct']:.1f}%")
    print(f"  Avg Latency: {p['latency']['mean']:.0f}ms")
```

### Analyze Specific Query

**Find all runs of one query:**
```python
import json

# Load raw results
with open('results/tools_v1_pipe_results.json') as f:
    data = json.load(f)

# Get specific query
query = "Find summer dresses for my wife's birthday party under $60"
query_data = [q for q in data['queries'] if query in q['query_text']][0]

# Analyze runs
for run in query_data['runs']:
    print(f"Run {run['run_number']}: {run['total_hits']} hits in {run['server_latency_ms']}ms")
    print(f"  Top product: {run['hits'][0]['_source']['productDisplayName']}")
    print(f"  Price: ${run['hits'][0]['_source']['price']}")
```

### Calculate Consistency Yourself

**Verify Jaccard similarity:**
```python
def jaccard(set_a, set_b):
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0

# Extract product IDs from runs
runs = query_data['runs']
doc_sets = [set(hit['_id'] for hit in run['hits']) for run in runs]

# Calculate all pairwise similarities
similarities = []
for i in range(len(doc_sets)):
    for j in range(i+1, len(doc_sets)):
        sim = jaccard(doc_sets[i], doc_sets[j])
        similarities.append(sim)

# Average
consistency = sum(similarities) / len(similarities)
print(f"Result consistency: {consistency*100:.1f}%")
```

### Extract Zero-Result Cases

**Find failures:**
```python
import json

with open('results/normal_pipe_results.json') as f:
    data = json.load(f)

zero_results = []
for query in data['queries']:
    for run in query['runs']:
        if run.get('success') and run.get('total_hits', 0) == 0:
            zero_results.append({
                'query': query['query_text'],
                'run': run['run_number'],
                'dsl': run.get('dsl_query')
            })

print(f"Found {len(zero_results)} zero-result cases:")
for case in zero_results[:5]:  # Show first 5
    print(f"\nQuery: {case['query'][:50]}...")
    print(f"Run: {case['run']}")
    print(f"DSL: {case['dsl'][:100]}...")
```

---

## Common Questions

### Q: Why do some queries have 0 hits but success=true?

**A:** Analytics queries return aggregation buckets, not product hits. The `hits` array is empty but `total_hits > 0` represents bucket count. We exclude these from zero-result calculations.

Example:
```json
{
  "query_text": "How many different types of shoes...",
  "total_hits": 9222,  // 9222 shoes in inventory
  "hits": [],  // Empty - returning aggregations, not products
  "aggregations": { "shoe_types": [...] }
}
```

### Q: Why does DSL consistency differ from result consistency?

**A:** The LLM may generate different DSL queries (different field orderings, match vs term queries, etc.) that return the same results.

Example:
```json
// Run 1 DSL
{"query": {"bool": {"must": [{"match": {"gender": "Women"}}, {"match": {"articleType": "Dresses"}}]}}}

// Run 2 DSL (different order, same results)
{"query": {"bool": {"must": [{"match": {"articleType": "Dresses"}}, {"match": {"gender": "Women"}}]}}}
```

Both return identical products. DSL consistency: 0% (different). Result consistency: 100% (same).

### Q: What's a good sample size for significance?

**A:** 10 runs per query gives 45 pairwise comparisons for consistency (10 choose 2). This is statistically sufficient to measure variance.

For 5 queries: 50 total runs = 5 × 45 = 225 comparisons.

### Q: How do I know if a difference is meaningful?

**Rules of thumb:**
- Consistency difference >10%: Meaningful (73% vs 40%)
- Latency difference >20%: Meaningful (2s vs 3.4s)
- Zero-result difference >5%: Meaningful (0% vs 12%)
- LLM score difference >0.5: Meaningful (4.0 vs 3.0)

### Q: Can I re-run just the LLM judge evaluation?

**A:** Yes! The raw results don't change. Just run:
```bash
cd scripts
python3 llm_judge_async_new.py
```

This will re-evaluate using the existing `analysis/llm_judging_input.json`.

### Q: How do I add my own query?

**Edit `run_experiments_parallel.py`:**
```python
QUERIES = [
    "Find summer dresses for my wife's birthday party under $60",
    "Show me the cheapest premium men's watches",
    "Your new query here",  # Add here
    ...
]
```

Then re-run experiments:
```bash
python3 run_experiments_parallel.py
python3 analyze_metrics.py
python3 llm_judge_async_new.py
```

### Q: What if I want to test a different pipeline?

**Edit `run_experiments_parallel.py`:**
```python
PIPELINES = [
    {"name": "your_new_pipe", "output": "../results/your_new_pipe_results.json"},
    ...
]
```

Make sure the pipeline exists in your OpenSearch cluster first.

---

## Summary

### Key Result Files

1. **`results/*.json`**: Raw data - look here for specific query behavior
2. **`metrics_analysis.json`**: Quantitative analysis - compare pipelines here
3. **`llm_judgments_full_NEW.json`**: Quality scores - understand why results are good/bad

### Most Important Metrics

1. **Result Consistency (73.1%)**: Primary metric for production readiness
2. **Zero-Result Rate (0%)**: Critical reliability indicator
3. **Avg Latency (1,939ms)**: User experience determinant
4. **LLM Judge Score (4.02/5)**: Overall quality assessment

### Reading Strategy

**For quick comparison:**
→ Read `metrics_analysis.json` overall metrics

**For understanding failures:**
→ Read `results/*.json` to see actual queries and hits

**For quality assessment:**
→ Read `llm_judgments_full_NEW.json` dimension scores

**For deep investigation:**
→ Cross-reference all three: metrics point to issues, raw results show what happened, judge explains why it matters

---

**Questions not answered here?** Open an issue in the repository!
