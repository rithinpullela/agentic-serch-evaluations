# Sample Examples: Comparing Approaches with Real Data

We tested all approaches on the same queries. Here's what actually happened.

---

## Example 1: Product Search

**Query:** "I need formal office wear for work presentations - men's shirts under $80"

### Quick Comparison

| Approach | Hits | Latency | Top Result | Top 10 Relevance |
|----------|------|---------|------------|------------------|
| **Tool-Based** | 648 | 1,469ms | Genesis Purple Shirts ($20) | [OK] 10/10 shirts |
| **Raw DSL (Haiku)** | 3,542 | 1,752ms | Flying Machine Brown Shirts ($20.87) | [!] 6/10 shirts, 1 trousers, 3 shoes |
| **Raw DSL (Sonnet)** | 2,216 | 3,234ms | Flying Machine Brown Shirts ($20.87) | [OK] 10/10 shirts |
| **Templates** | 3,542 | 2,860ms | Peter England Blue Shirts ($40.21) | [X] 1/10 shirts, 9 shoes |

### What Happened

**Tool-Based:** Extracted precise parameters (gender=Men, articleType=Shirts, usage=Formal, max_price=80) Result: Backend generated exact filters Result: All 10 results are actually shirts Result: Fast (1.5s)

**Raw DSL (Haiku):** Generated text search for "formal office wear shirts" Result: Loose matching with "or" operator Result: Returned trousers and shoes mixed with shirts Result: Over-broad (3,542 hits)

**Raw DSL (Sonnet):** Smarter - added articleType filter and used fuzziness Result: All 10 are shirts Result: But 2x slower than Tool-Based (3.2s) and less precise (2,216 vs 648 hits)

**Templates:** Similar text matching with field boosting Result: Worst results - 90% of top results are shoes, not shirts Result: 2x slower latency

**Key Insight:** Tool-based achieved **3.4x better precision** (648 vs 2,216 hits) even compared to Sonnet, and was **2.2x faster**. Structured filters beat even the smartest text matching.

### DSL Queries Generated

**Tool-Based:**
```json
{
  "query": {
    "bool": {
      "filter": [
        {"term": {"gender.keyword": "Men"}},
        {"term": {"articleType.keyword": "Shirts"}},
        {"term": {"usage.keyword": "Formal"}},
        {"range": {"price": {"lte": 80}}}
      ]
    }
  },
  "sort": [{"price": "asc"}],
  "size": 20
}
```
Result: Clean structured filters = precise results (all 10 are shirts)

**Raw DSL (Haiku):**
```json
{
  "query": {
    "bool": {
      "must": [
        {
          "multi_match": {
            "query": "formal office wear shirts",
            "fields": ["productDisplayName", "articleType", "usage"],
            "operator": "or"
          }
        }
      ],
      "filter": [
        {"term": {"gender.keyword": "Men"}},
        {"range": {"price": {"lte": 80}}}
      ]
    }
  },
  "sort": [{"avgRating": "desc"}, {"price": "asc"}],
  "size": 10
}
```
Result: Text matching with "or" operator = loose results (6 shirts + 1 trousers + 3 shoes)

**Raw DSL (Sonnet):**
```json
{
  "query": {
    "bool": {
      "must": [
        {
          "multi_match": {
            "query": "formal office work presentations shirts",
            "fields": ["productDisplayName", "usage", "articleType"],
            "fuzziness": "AUTO"
          }
        }
      ],
      "filter": [
        {"term": {"gender.keyword": "Men"}},
        {"terms": {"articleType.keyword": ["Shirts", "Formal Shirts"]}},
        {"range": {"price": {"lte": 80}}}
      ]
    }
  },
  "sort": [{"avgRating": "desc"}, {"price": "asc"}],
  "size": 10
}
```
Result: Smarter - added articleType filter Result: All 10 are shirts Result: But 2x slower (3.2s) and less precise (2,216 hits)

**Templates:**
```json
{
  "query": {
    "bool": {
      "must": [
        {
          "multi_match": {
            "query": "formal office wear shirts",
            "fields": [
              "articleType^3",
              "masterCategory^2",
              "subCategory^2",
              "productDisplayName^1.5",
              "usage",
              "baseColour"
            ],
            "operator": "or"
          }
        }
      ],
      "filter": [
        {"term": {"gender.keyword": "Men"}},
        {"range": {"price": {"lte": 80}}}
      ]
    }
  },
  "size": 20
}
```
Result: Text matching with field boosting = worst results (1 shirt + 9 shoes) + slowest

---

## Example 2: Analytics Query

**Query:** "How many different types of shoes do we have and what are their average prices?"

### Quick Comparison

| Approach | Success Rate | First Run Hits | Latency | Result Type |
|----------|--------------|----------------|---------|-------------|
| **Tool-Based** | 100% (10/10) | 9,222 | 1,781ms | [OK] Aggregations |
| **Raw DSL (Haiku)** | 30% (3/10) | 0 | 1,421ms | [X] Failed filter |
| **Raw DSL (Sonnet)** | 100% (10/10) | 9,222 | 3,339ms | [OK] Works (but slower) |
| **Templates** | 100% (10/10) | 9,222 | 4,803ms | [OK] Works (but 2.7x slower) |

### What Happened

**Tool-Based:** Backend knows `articleType` values are "Casual Shoes", "Formal Shoes", etc. Result: Filters on `masterCategory=Footwear` Result: 100% success

**Raw DSL (Haiku):** Generated filter `articleType="Shoes"` Result: But no products have `articleType="Shoes"` (they're "Casual Shoes", "Formal Shoes") Result: **70% of runs returned zero results**

**Raw DSL (Sonnet):** Smarter - avoided the bad filter Result: Works but 2x slower than tool-based

**Templates:** Works but extremely slow (4.8 seconds)

**Key Insight:** Tool backend has **domain knowledge baked in** (correct field values). Raw DSL LLM guesses and gets it wrong 70% of the time.

### DSL Queries Generated

**Tool-Based (100% success):**
```json
{
  "size": 0,
  "query": {
    "bool": {
      "filter": [
        {"term": {"masterCategory.keyword": "Footwear"}}
      ]
    }
  },
  "aggs": {
    "primary_group": {
      "terms": {"field": "articleType.keyword", "size": 20},
      "aggs": {
        "avg_price": {"avg": {"field": "price"}},
        "avg_rating": {"avg": {"field": "avgRating"}},
        "total_reviews": {"sum": {"field": "numRatings"}},
        "price_stats": {"stats": {"field": "price"}}
      }
    }
  }
}
```
Result: Correct filter (masterCategory=Footwear) Result: 100% success, rich aggregations

**Raw DSL Haiku (30% success, 70% failure):**

*Failed runs (7 out of 10):*
```json
{
  "size": 0,
  "query": {
    "bool": {
      "filter": [
        {"term": {"articleType.keyword": "Shoes"}}
      ]
    }
  },
  "aggs": {
    "shoe_types": {
      "terms": {"field": "subCategory.keyword"},
      "aggs": {"avg_price": {"avg": {"field": "price"}}}
    }
  }
}
```
Result: Wrong filter (articleType="Shoes" doesn't exist) Result: 0 results

*Successful runs (3 out of 10):*
```json
{
  "size": 0,
  "query": {
    "bool": {
      "filter": [
        {"term": {"masterCategory.keyword": "Footwear"}}
      ]
    }
  },
  "aggs": {
    "shoe_types": {
      "terms": {"field": "articleType.keyword", "size": 100},
      "aggs": {"average_price": {"avg": {"field": "price"}}}
    }
  }
}
```
Result: Correct filter (inconsistently generated)

**Raw DSL (Sonnet) (100% success):**
```json
{
  "size": 0,
  "query": {
    "bool": {
      "filter": [
        {"term": {"masterCategory.keyword": "Footwear"}}
      ]
    }
  },
  "aggs": {
    "shoe_types": {
      "terms": {"field": "articleType.keyword", "size": 1000},
      "aggs": {"avg_price": {"avg": {"field": "price"}}}
    }
  }
}
```
Result: Correct filter, consistent behavior Result: But 2x slower than Tool-Based (3.3s vs 1.8s)

**Templates (100% success, but slow):**
```json
{
  "size": 0,
  "query": {
    "bool": {
      "filter": [
        {"term": {"masterCategory.keyword": "Footwear"}}
      ]
    }
  },
  "aggs": {
    "shoe_types": {
      "terms": {"field": "subCategory.keyword", "size": 100},
      "aggs": {"avg_price": {"avg": {"field": "price"}}}
    }
  }
}
```
Result: Correct filter, but groups by subCategory instead of articleType Result: Works but 2.7x slower (4.8s)

---

## Summary

### Product Search: Formal Office Wear

| Approach | Precision | Relevance | Speed | Notes |
|----------|-----------|-----------|-------|-------|
| **Tool-Based** | 648 hits | 10/10 shirts | 1,469ms | Best: precise + fast |
| **Raw DSL (Haiku)** | 3,542 hits | 6/10 shirts | 1,752ms | Over-broad, mixed irrelevant items |
| **Raw DSL (Sonnet)** | 2,216 hits | 10/10 shirts | 3,234ms | Good relevance, but 2x slower |
| **Templates** | 3,542 hits | 1/10 shirts | 2,860ms | Worst: 90% shoes in results |

**Winner:** Tool-Based - 3.4x more precise than Sonnet, 2.2x faster

### Analytics Query: Shoe Types

| Approach | Success Rate | Speed | Notes |
|----------|--------------|-------|-------|
| **Tool-Based** | 100% (10/10) | 1,781ms | Knows correct field values |
| **Raw DSL (Haiku)** | 30% (3/10) | 1,421ms | 70% failures - wrong filter |
| **Raw DSL (Sonnet)** | 100% (10/10) | 3,339ms | Works but 2x slower |
| **Templates** | 100% (10/10) | 4,803ms | Works but 2.7x slower |

**Winner:** Tool-Based - 100% success, fastest

### The Core Difference

**Tool backend:** Engineering-level precision, domain knowledge baked in, consistent behavior

**Raw DSL (Haiku):** LLM guessing, inconsistent, frequent failures

**Raw DSL (Sonnet):** Smarter guessing, more reliable, but slower and less precise

**Templates:** Consistent structure but slow, imprecise text matching
