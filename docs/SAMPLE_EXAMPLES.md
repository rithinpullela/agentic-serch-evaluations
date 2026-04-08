# Sample Examples: Comparing Approaches with Real Data

We tested all approaches on the same queries. Here's what actually happened.

---

## Example 1: Product Search - "Formal office wear for men under $80"

### Quick Comparison

| Approach | Hits | Latency | Top Result | Top 10 Relevance |
|----------|------|---------|------------|------------------|
| **Tool-Based** | 648 | 1,469ms | Genesis Purple Shirts ($20) | ✅ 10/10 shirts |
| **Raw DSL (Haiku)** | 3,542 | 1,752ms | Flying Machine Brown Shirts ($20.87) | ⚠️ 6/10 shirts, 1 trousers, 3 shoes |
| **Templates** | 3,542 | 2,860ms | Peter England Blue Shirts ($40.21) | ❌ 1/10 shirts, 9 shoes |

### What Happened

**Tool-Based:** Extracted precise parameters (gender=Men, articleType=Shirts, usage=Formal, max_price=80) → Backend generated exact filters → All 10 results are actually shirts

**Raw DSL:** Generated text search for "formal office wear shirts" → Loose matching → Returned trousers and shoes mixed with shirts

**Templates:** Similar text matching → Even worse - 90% of top results are shoes, not shirts → 2x slower latency

**Key Insight:** Tool-based achieved **5.5x better precision** (648 vs 3,542 hits) because it used structured filters instead of text matching.

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
→ Clean structured filters = precise results (all 10 are shirts)

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
→ Text matching with "or" operator = loose results (6 shirts + 1 trousers + 3 shoes)

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
→ Text matching with field boosting = worst results (1 shirt + 9 shoes) + slowest

---

## Example 2: Analytics Query - "How many shoe types and average prices?"

### Quick Comparison

| Approach | Success Rate | First Run Hits | Latency | Result Type |
|----------|--------------|----------------|---------|-------------|
| **Tool-Based** | 100% (10/10) | 9,222 | 1,781ms | ✅ Aggregations |
| **Raw DSL (Haiku)** | 30% (3/10) | 0 | 1,421ms | ❌ Failed filter |
| **Raw DSL (Sonnet)** | 100% (10/10) | 9,222 | 3,339ms | ✅ Works (but slower) |
| **Templates** | 100% (10/10) | 9,222 | 4,803ms | ✅ Works (but 2.7x slower) |

### What Happened

**Tool-Based:** Backend knows `articleType` values are "Casual Shoes", "Formal Shoes", etc. → Filters on `masterCategory=Footwear` → 100% success

**Raw DSL (Haiku):** Generated filter `articleType="Shoes"` → But no products have `articleType="Shoes"` (they're "Casual Shoes", "Formal Shoes") → **70% of runs returned zero results**

**Raw DSL (Sonnet):** Smarter - avoided the bad filter → Works but 2x slower than tool-based

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
→ Correct filter (masterCategory=Footwear) → 100% success, rich aggregations

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
→ Wrong filter (articleType="Shoes" doesn't exist) → 0 results

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
→ Correct filter (inconsistently generated)

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
→ Correct filter, but groups by subCategory instead of articleType → Works but 2.7x slower (4.8s)

---

## Summary

### Product Search Results

Tool-based:
- 5.5x more precise (648 vs 3,542 hits)
- 100% relevance (all results are shirts)
- Fastest (1.5 seconds)

Raw DSL / Templates:
- Over-broad results
- Mixed irrelevant items (trousers, shoes)
- 2x slower (templates)

### Analytics Query Results

Tool-based:
- 100% success rate
- Knows correct field values
- Fast (1.8 seconds)

Raw DSL (Haiku):
- 70% failure rate (zero results)
- Guesses wrong field values
- Inconsistent behavior

**The Difference:** Tool backend has **engineering-level precision** and **domain knowledge**. Raw DSL has **LLM-level guessing**.
