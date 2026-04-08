#!/usr/bin/env python3
"""
Improved LLM Judge Prompt - Grounded with Decision Trees
Based on research: G-Eval, Prometheus, and best practices from Eugene Yan, Hamel Husain

Key Improvements:
1. Chain-of-thought BEFORE scoring (not after)
2. Decision trees with yes/no questions (not arbitrary 1-5 scales)
3. Explicit mapping from answers to scores (deterministic)
4. Structured reasoning in JSON output (debuggable)
5. Query-type awareness (future: load different rubrics per type)

Expected Impact:
- Reduce score variance from 0.5-0.7 to <0.3 standard deviation
- Improve inter-run consistency by 40-60%
- Make judgments interpretable and debuggable
"""

# Drop-in replacement for JUDGE_PROMPT_TEMPLATE in llm_judge_async.py
IMPROVED_JUDGE_PROMPT_TEMPLATE = """You are evaluating search results for an e-commerce fashion query.

Query: "{query}"

Results Returned:
{results}

Total hits: {total_hits}

---

EVALUATION PROCESS:

Follow this decision tree to evaluate the results. Answer each question with clear reasoning BEFORE assigning scores.

**STEP 1: RELEVANCE EVALUATION**

Answer these questions:
Q1. Are all returned products of the correct product type requested in the query?
    (Example: If query asks for "dresses", are all results dresses? Not skirts, tops, etc.)
    Your answer: [Yes/No + explain]

Q2. Do results match the target demographic specified or implied in the query?
    (Example: "men's watches" should return men's items, "my wife" implies women's items)
    Your answer: [Yes/No + explain]

Q3. If the query specifies an occasion/usage (party, running, formal), do results match?
    Your answer: [Yes/No/Not Applicable + explain]

Based on your answers above, assign:
- All Yes/NA → Relevance Score = 5
- Q1 Yes, Q2 Yes, Q3 No → Relevance Score = 4
- Q1 Yes, Q2 or Q3 No → Relevance Score = 3
- Q1 No but related products → Relevance Score = 2
- Q1 No, wrong product type → Relevance Score = 1

Your Relevance Score: ___

---

**STEP 2: PRECISION EVALUATION (Constraint Matching)**

Answer these questions:
Q1. If query specifies price constraints (under $X, cheap, budget), do ALL results meet it?
    Your answer: [Yes/No/Not Applicable + explain]

Q2. If query specifies attributes (color, material, brand), do results match?
    Your answer: [Yes/No/Not Applicable + explain]

Q3. Are results free from obvious mismatches to explicit query requirements?
    Your answer: [Yes/No + explain]

Based on your answers:
- All constraints perfectly met → Precision Score = 5
- 1-2 minor violations → Precision Score = 4
- 3-4 violations or 1 major → Precision Score = 3
- Many violations → Precision Score = 2
- Most results violate constraints → Precision Score = 1

Your Precision Score: ___

---

**STEP 3: QUALITY EVALUATION**

Answer these questions:
Q1. Do results show reasonable variety in options (not all same brand/color/price point)?
    Your answer: [Yes/No + explain]

Q2. Are product ratings generally acceptable (mostly 3.5+ stars if ratings available)?
    Your answer: [Yes/No/Ratings Not Available + explain]

Q3. Is the selection size sufficient to give user meaningful choice?
    Your answer: [Yes/No + explain]

Based on your answers:
- All Yes → Quality Score = 5
- 2 of 3 Yes → Quality Score = 4
- 1 of 3 Yes → Quality Score = 3
- Mix of concerning issues → Quality Score = 2
- Poor variety, bad ratings, insufficient results → Quality Score = 1

Your Quality Score: ___

---

**STEP 4: COMPLETENESS EVALUATION**

Q1. Does the result set cover the main aspects of the query?
    (Example: "party dresses" should have variety of party-appropriate styles)
    Your answer: [Yes/No + explain]

Q2. Are important product attributes filled in and helpful for decision-making?
    Your answer: [Yes/No + explain]

Q3. Given the total_hits count, does the returned set represent the available inventory well?
    Your answer: [Yes/No + explain]

Based on your answers:
- Comprehensive coverage → Completeness Score = 5
- Good coverage, minor gaps → Completeness Score = 4
- Acceptable but missing aspects → Completeness Score = 3
- Missing important aspects → Completeness Score = 2
- Very incomplete → Completeness Score = 1

Your Completeness Score: ___

---

**FINAL OUTPUT**

Respond ONLY with valid JSON (no markdown code blocks):
{{
  "relevance_analysis": {{
    "q1_product_type_match": "your answer to relevance Q1",
    "q2_demographic_match": "your answer to relevance Q2",
    "q3_occasion_match": "your answer to relevance Q3",
    "relevance_score": <1-5>
  }},
  "precision_analysis": {{
    "q1_price_constraints": "your answer to precision Q1",
    "q2_attribute_constraints": "your answer to precision Q2",
    "q3_no_obvious_mismatches": "your answer to precision Q3",
    "precision_score": <1-5>
  }},
  "quality_analysis": {{
    "q1_variety": "your answer to quality Q1",
    "q2_ratings": "your answer to quality Q2",
    "q3_selection_size": "your answer to quality Q3",
    "quality_score": <1-5>
  }},
  "completeness_analysis": {{
    "q1_query_coverage": "your answer to completeness Q1",
    "q2_attribute_completeness": "your answer to completeness Q2",
    "q3_inventory_representation": "your answer to completeness Q3",
    "completeness_score": <1-5>
  }},
  "overall_score": <average of 4 dimension scores>,
  "critical_issues": ["list any dealbreaker problems"],
  "suggestions": ["list potential improvements"]
}}"""


def extract_improved_judgment(response_text, query, run_num, total_hits):
    """
    Extract scores from improved prompt's nested JSON structure.

    This handles the new format where reasoning is embedded in analysis objects.

    Args:
        response_text: Raw LLM response text
        query: Original query text
        run_num: Run number for this query
        total_hits: Total hits returned

    Returns:
        dict: Extracted scores and reasoning in flat format for compatibility
    """
    import json

    # Find JSON boundaries
    start_idx = response_text.find('{')
    end_idx = response_text.rfind('}') + 1

    if start_idx < 0 or end_idx <= start_idx:
        raise ValueError("No valid JSON found in response")

    json_str = response_text[start_idx:end_idx]
    judgment = json.loads(json_str)

    # Extract dimension scores from nested analysis objects
    scores = {
        'relevance_score': judgment['relevance_analysis']['relevance_score'],
        'precision_score': judgment['precision_analysis']['precision_score'],
        'quality_score': judgment['quality_analysis']['quality_score'],
        'completeness_score': judgment['completeness_analysis']['completeness_score'],
        'overall_score': judgment['overall_score'],

        # Store structured reasoning for debugging
        'reasoning': {
            'relevance': judgment['relevance_analysis'],
            'precision': judgment['precision_analysis'],
            'quality': judgment['quality_analysis'],
            'completeness': judgment['completeness_analysis']
        },

        # Extract issues and suggestions
        'issues': judgment.get('critical_issues', []),
        'suggestions': judgment.get('suggestions', []),

        # Metadata
        'query': query,
        'run_number': run_num,
        'total_hits': total_hits,
        'prompt_version': 'improved_decision_tree_v1'
    }

    return scores


# Query classification for future query-type specific rubrics
def classify_query_type(query_text):
    """
    Classify query to select appropriate evaluation rubric.

    Future enhancement: Load different prompt templates based on query type.

    Args:
        query_text: User's search query

    Returns:
        str: Query type classification
    """
    query_lower = query_text.lower()

    # Check for analytics queries first (different evaluation)
    analytics_patterns = ['how many', 'average', 'total', 'count', 'show me the distribution']
    if any(pattern in query_lower for pattern in analytics_patterns):
        return 'analytics'

    # Constraint-heavy queries (price, size, specific attributes)
    constraint_words = ['under', 'cheap', 'budget', 'less than', 'maximum', '$', 'size', 'between']
    if any(word in query_lower for word in constraint_words):
        return 'constraint_focused'

    # Quality-focused queries (ratings, reviews, best)
    quality_words = ['best', 'top rated', 'highest', 'good reviews', 'well-reviewed', 'highly rated']
    if any(word in query_lower for word in quality_words):
        return 'quality_focused'

    # Style/occasion queries (party, casual, formal, seasonal)
    style_words = ['party', 'wedding', 'casual', 'formal', 'summer', 'winter', 'spring', 'fall', 'office', 'beach']
    if any(word in query_lower for word in style_words):
        return 'style_focused'

    return 'general'


if __name__ == "__main__":
    # Example usage
    print("=" * 80)
    print("IMPROVED JUDGE PROMPT - Decision Tree Based")
    print("=" * 80)
    print("\nKey Features:")
    print("  ✓ Chain-of-thought before scoring")
    print("  ✓ Yes/no questions instead of arbitrary scales")
    print("  ✓ Deterministic score mapping")
    print("  ✓ Structured reasoning in output")
    print("  ✓ Query-type classification ready")
    print("\nTo use: Replace JUDGE_PROMPT_TEMPLATE in llm_judge_async.py")
    print("        Update JSON extraction with extract_improved_judgment()")
    print("\nExpected improvement: 40-60% reduction in score variance")
    print("=" * 80)
