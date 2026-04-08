#!/usr/bin/env python3
"""
Async LLM-as-Judge for evaluating result quality with parallel processing
Uses Claude Sonnet 4.6 via AWS Bedrock (Opus 4.6 not available)
"""

import json
import os
from pathlib import Path
import asyncio
from concurrent.futures import ThreadPoolExecutor
import statistics

try:
    import boto3
    BEDROCK_AVAILABLE = True
except ImportError:
    BEDROCK_AVAILABLE = False


# Same prompt template
JUDGE_PROMPT_TEMPLATE = 'You are evaluating search results for an e-commerce fashion query.\n\nQuery: "{query}"\n\nResults Returned:\n{results}\n\nTotal hits: {total_hits}\n\n---\n\nEVALUATION PROCESS:\n\nFollow this decision tree to evaluate the results. Answer each question with clear reasoning BEFORE assigning scores.\n\n**STEP 1: RELEVANCE EVALUATION**\n\nAnswer these questions:\nQ1. Are all returned products of the correct product type requested in the query?\n    (Example: If query asks for "dresses", are all results dresses? Not skirts, tops, etc.)\n    Your answer: [Yes/No + explain]\n\nQ2. Do results match the target demographic specified or implied in the query?\n    (Example: "men\'s watches" should return men\'s items, "my wife" implies women\'s items)\n    Your answer: [Yes/No + explain]\n\nQ3. If the query specifies an occasion/usage (party, running, formal), do results match?\n    Your answer: [Yes/No/Not Applicable + explain]\n\nBased on your answers above, assign:\n- All Yes/NA → Relevance Score = 5\n- Q1 Yes, Q2 Yes, Q3 No → Relevance Score = 4\n- Q1 Yes, Q2 or Q3 No → Relevance Score = 3\n- Q1 No but related products → Relevance Score = 2\n- Q1 No, wrong product type → Relevance Score = 1\n\nYour Relevance Score: ___\n\n---\n\n**STEP 2: PRECISION EVALUATION (Constraint Matching)**\n\nAnswer these questions:\nQ1. If query specifies price constraints (under $X, cheap, budget), do ALL results meet it?\n    Your answer: [Yes/No/Not Applicable + explain]\n\nQ2. If query specifies attributes (color, material, brand), do results match?\n    Your answer: [Yes/No/Not Applicable + explain]\n\nQ3. Are results free from obvious mismatches to explicit query requirements?\n    Your answer: [Yes/No + explain]\n\nBased on your answers:\n- All constraints perfectly met → Precision Score = 5\n- 1-2 minor violations → Precision Score = 4\n- 3-4 violations or 1 major → Precision Score = 3\n- Many violations → Precision Score = 2\n- Most results violate constraints → Precision Score = 1\n\nYour Precision Score: ___\n\n---\n\n**STEP 3: QUALITY EVALUATION**\n\nAnswer these questions:\nQ1. Do results show reasonable variety in options (not all same brand/color/price point)?\n    Your answer: [Yes/No + explain]\n\nQ2. Are product ratings generally acceptable (mostly 3.5+ stars if ratings available)?\n    Your answer: [Yes/No/Ratings Not Available + explain]\n\nQ3. Is the selection size sufficient to give user meaningful choice?\n    Your answer: [Yes/No + explain]\n\nBased on your answers:\n- All Yes → Quality Score = 5\n- 2 of 3 Yes → Quality Score = 4\n- 1 of 3 Yes → Quality Score = 3\n- Mix of concerning issues → Quality Score = 2\n- Poor variety, bad ratings, insufficient results → Quality Score = 1\n\nYour Quality Score: ___\n\n---\n\n**STEP 4: COMPLETENESS EVALUATION**\n\nQ1. Does the result set cover the main aspects of the query?\n    (Example: "party dresses" should have variety of party-appropriate styles)\n    Your answer: [Yes/No + explain]\n\nQ2. Are important product attributes filled in and helpful for decision-making?\n    Your answer: [Yes/No + explain]\n\nQ3. Given the total_hits count, does the returned set represent the available inventory well?\n    Your answer: [Yes/No + explain]\n\nBased on your answers:\n- Comprehensive coverage → Completeness Score = 5\n- Good coverage, minor gaps → Completeness Score = 4\n- Acceptable but missing aspects → Completeness Score = 3\n- Missing important aspects → Completeness Score = 2\n- Very incomplete → Completeness Score = 1\n\nYour Completeness Score: ___\n\n---\n\n**FINAL OUTPUT**\n\nRespond ONLY with valid JSON (no markdown code blocks):\n{{\n  "relevance_analysis": {{\n    "q1_product_type_match": "your answer to relevance Q1",\n    "q2_demographic_match": "your answer to relevance Q2",\n    "q3_occasion_match": "your answer to relevance Q3",\n    "relevance_score": <1-5>\n  }},\n  "precision_analysis": {{\n    "q1_price_constraints": "your answer to precision Q1",\n    "q2_attribute_constraints": "your answer to precision Q2",\n    "q3_no_obvious_mismatches": "your answer to precision Q3",\n    "precision_score": <1-5>\n  }},\n  "quality_analysis": {{\n    "q1_variety": "your answer to quality Q1",\n    "q2_ratings": "your answer to quality Q2",\n    "q3_selection_size": "your answer to quality Q3",\n    "quality_score": <1-5>\n  }},\n  "completeness_analysis": {{\n    "q1_query_coverage": "your answer to completeness Q1",\n    "q2_attribute_completeness": "your answer to completeness Q2",\n    "q3_inventory_representation": "your answer to completeness Q3",\n    "completeness_score": <1-5>\n  }},\n  "overall_score": <average of 4 dimension scores>,\n  "critical_issues": ["list any dealbreaker problems"],\n  "suggestions": ["list potential improvements"]\n}}'


def format_results(results):
    """Format results for LLM display"""
    if not results:
        return "No results returned"

    formatted = []
    for idx, result in enumerate(results, 1):
        parts = [f"\n{idx}. {result.get('product_name', 'Unknown Product')}"]

        if result.get('price'):
            parts.append(f"   Price: ${result['price']:.2f}")

        details = []
        if result.get('gender'):
            details.append(f"Gender: {result['gender']}")
        if result.get('article_type'):
            details.append(f"Type: {result['article_type']}")
        if result.get('color'):
            details.append(f"Color: {result['color']}")
        if result.get('season'):
            details.append(f"Season: {result['season']}")
        if result.get('usage'):
            details.append(f"Usage: {result['usage']}")

        if details:
            parts.append(f"   {', '.join(details)}")

        if result.get('rating'):
            parts.append(f"   Rating: {result['rating']:.1f}/5 ({result.get('num_ratings', 0)} reviews)")

        formatted.append('\n'.join(parts))

    return '\n'.join(formatted)


def judge_single_result(client, query_data, idx, total):
    """Judge a single query result (thread-safe)"""
    query = query_data['query']
    run_num = query_data.get('run_number', 1)
    results = query_data['top_results']
    total_hits = query_data['total_hits']
    is_zero_results = query_data.get('zero_results', False)
    skip_evaluation = query_data.get('skip_evaluation', False)

    # Skip analytics queries - they need different evaluation criteria
    if skip_evaluation:
        scores = {
            "relevance_score": None,
            "precision_score": None,
            "quality_score": None,
            "completeness_score": None,
            "overall_score": None,
            "reasoning": "Analytics query - skipped product search evaluation",
            "issues": [],
            "query": query,
            "run_number": run_num,
            "total_hits": total_hits,
            "query_type": "analytics"
        }
        return (idx, scores, None)

    # Automatically assign 0 score for zero-result runs
    if is_zero_results:
        scores = {
            "relevance_score": 0,
            "precision_score": 0,
            "quality_score": 0,
            "completeness_score": 0,
            "overall_score": 0.0,
            "reasoning": "No results returned - automatic 0 score",
            "issues": ["Zero results returned for this query"],
            "query": query,
            "run_number": run_num,
            "total_hits": 0
        }
        return (idx, scores, None)

    formatted_results = format_results(results)

    prompt = JUDGE_PROMPT_TEMPLATE.format(
        query=query,
        results=formatted_results,
        total_hits=total_hits
    )

    try:
        # Bedrock converse API
        response = client.converse(
            modelId="us.anthropic.claude-sonnet-4-20250514-v1:0",
            messages=[{
                "role": "user",
                "content": [{"text": prompt}]
            }],
            inferenceConfig={
                "maxTokens": 1024,
                "temperature": 0
            }
        )

        response_text = response['output']['message']['content'][0]['text']

        # Extract JSON with improved nested structure
        try:
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}') + 1
            
            if start_idx >= 0 and end_idx > start_idx:
                json_str = response_text[start_idx:end_idx]
                judgment = json.loads(json_str)
                
                # Handle both old flat format and new nested format
                if 'relevance_analysis' in judgment:
                    # New improved format
                    scores = {
                        'relevance_score': judgment['relevance_analysis']['relevance_score'],
                        'precision_score': judgment['precision_analysis']['precision_score'],
                        'quality_score': judgment['quality_analysis']['quality_score'],
                        'completeness_score': judgment['completeness_analysis']['completeness_score'],
                        'overall_score': judgment['overall_score'],
                        'reasoning': str(judgment),  # Store full reasoning
                        'issues': judgment.get('critical_issues', []),
                        'query': query,
                        'run_number': run_num,
                        'total_hits': total_hits
                    }
                else:
                    # Old flat format (backwards compat)
                    scores = judgment
                    scores['query'] = query
                    scores['run_number'] = run_num
                    scores['total_hits'] = total_hits
                
                return (idx, scores, None)
        except Exception as e:
            return (idx, None, f"JSON parse error: {str(e)}")
        else:
            return (idx, None, "Could not parse JSON")

    except Exception as e:
        return (idx, None, str(e))


async def judge_all_async(input_file="../analysis_final/llm_judging_input.json", region="us-west-2", max_workers=10):
    """Judge all pipelines with parallel processing"""

    if not BEDROCK_AVAILABLE:
        print("❌ boto3 not available")
        return

    print("🔧 Using AWS Bedrock API with async parallelization")
    print(f"⚡ Max parallel workers: {max_workers}")

    # Initialize client
    try:
        client = boto3.client('bedrock-runtime', region_name=region)
        print(f"✅ Bedrock client initialized (region: {region})")
        print(f"📊 Model: Claude Sonnet 4.6 (Opus not available)\n")
    except Exception as e:
        print(f"❌ Bedrock initialization failed: {e}")
        return

    # Load judging data
    if not Path(input_file).exists():
        print(f"❌ Error: {input_file} not found")
        return

    with open(input_file, 'r') as f:
        judging_data = json.load(f)

    all_judgments = {}

    print("🤖 Starting LLM-as-Judge evaluation...")
    print("=" * 80)

    for pipeline_name, queries_data in judging_data.items():
        print(f"\n📊 Judging pipeline: {pipeline_name}")

        unique_queries = set(q['query'] for q in queries_data)
        total_evaluations = len(queries_data)

        print(f"   {len(unique_queries)} unique queries × multiple runs = {total_evaluations} evaluations")
        print(f"   Processing in parallel (max {max_workers} concurrent)...\n")

        # Use ThreadPoolExecutor for parallel Bedrock calls
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            futures = [
                loop.run_in_executor(
                    executor,
                    judge_single_result,
                    client,
                    query_data,
                    idx,
                    total_evaluations
                )
                for idx, query_data in enumerate(queries_data, 1)
            ]

            # Gather results with progress
            pipeline_judgments = []
            completed = 0

            for future in asyncio.as_completed(futures):
                idx, judgment, error = await future
                completed += 1

                if judgment:
                    pipeline_judgments.append(judgment)
                    if judgment.get('total_hits', 0) == 0:
                        print(f"  [{completed}/{total_evaluations}] ⓪ {judgment['query'][:50]}... (run {judgment['run_number']}) Score: 0.0/5 (zero results)")
                    else:
                        overall = judgment.get('overall_score', 'N/A')
                        score_str = f"{overall:.1f}/5" if isinstance(overall, (int, float)) else str(overall)
                        print(f"  [{completed}/{total_evaluations}] ✓ {judgment['query'][:50]}... (run {judgment['run_number']}) Score: {score_str}")
                else:
                    print(f"  [{completed}/{total_evaluations}] ✗ Failed: {error}")

        all_judgments[pipeline_name] = pipeline_judgments

    # Save judgments
    output_file = "../analysis_final/llm_judgments_full_NEW.json"
    with open(output_file, 'w') as f:
        json.dump(all_judgments, f, indent=2)

    print("\n" + "=" * 80)
    print(f"✅ Judging complete! Saved to: {output_file}")

    # Print summary
    print("\n" + "=" * 80)
    print("📊 JUDGMENT SUMMARY (All Runs)")
    print("=" * 80 + "\n")

    print(f"{'Pipeline':<20} | {'Relevance':<10} | {'Precision':<10} | {'Quality':<10} | {'Overall':<10} | {'Std Dev':<10}")
    print(f"{'-'*20}-+-{'-'*10}-+-{'-'*10}-+-{'-'*10}-+-{'-'*10}-+-{'-'*10}")

    for pipeline_name, judgments in all_judgments.items():
        if judgments:
            # Filter out None scores (analytics queries)
            scored_judgments = [j for j in judgments if j.get('overall_score') is not None]

            if scored_judgments:
                avg_relevance = sum(j['relevance_score'] for j in scored_judgments) / len(scored_judgments)
                avg_precision = sum(j['precision_score'] for j in scored_judgments) / len(scored_judgments)
                avg_quality = sum(j['quality_score'] for j in scored_judgments) / len(scored_judgments)
                avg_overall = sum(j['overall_score'] for j in scored_judgments) / len(scored_judgments)

                std_dev = statistics.stdev([j['overall_score'] for j in scored_judgments]) if len(scored_judgments) > 1 else 0

                print(f"{pipeline_name:<20} | {avg_relevance:<10.2f} | {avg_precision:<10.2f} | {avg_quality:<10.2f} | {avg_overall:<10.2f} | {std_dev:<10.2f}")
            else:
                print(f"{pipeline_name:<20} | No scored queries (all analytics)")

    # Per-query consistency
    print("\n" + "=" * 80)
    print("📊 QUALITY CONSISTENCY (Per Query)")
    print("=" * 80)

    for pipeline_name, judgments in all_judgments.items():
        print(f"\n🔧 {pipeline_name.upper()}")
        print("-" * 80)

        from collections import defaultdict
        query_scores = defaultdict(list)
        for j in judgments:
            # Skip analytics queries (None scores)
            if j.get('overall_score') is not None:
                query_scores[j['query']].append(j['overall_score'])

        for query, scores in query_scores.items():
            if scores:
                mean = sum(scores) / len(scores)
                std = statistics.stdev(scores) if len(scores) > 1 else 0
                print(f"  {query[:60]:<62} | Mean: {mean:.2f} | Std: {std:.2f} | Range: {min(scores):.1f}-{max(scores):.1f}")

    return all_judgments


if __name__ == "__main__":
    import sys

    AWS_REGION = "us-west-2"
    MAX_WORKERS = 10  # Parallel LLM calls

    asyncio.run(judge_all_async(region=AWS_REGION, max_workers=MAX_WORKERS))
