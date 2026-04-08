#!/usr/bin/env python3
"""
Analyze experiment results - computes all metrics
Metrics: Latency, Reproducibility, Error Rates, and prepares data for LLM judging
"""

import json
import hashlib
from pathlib import Path
from collections import defaultdict
import statistics


def load_results(filename):
    """Load experiment results from JSON file"""
    with open(filename, 'r') as f:
        return json.load(f)


def analyze_latency(results):
    """Compute latency metrics"""
    all_latencies = []
    query_latencies = defaultdict(list)

    for query in results['queries']:
        for run in query['runs']:
            if run.get('success'):
                latency = run['server_latency_ms']
                all_latencies.append(latency)
                query_latencies[query['query_text']].append(latency)

    if not all_latencies:
        return {
            "error": "No successful runs",
            "per_query": {}
        }

    all_latencies_sorted = sorted(all_latencies)
    n = len(all_latencies_sorted)

    metrics = {
        "mean": statistics.mean(all_latencies),
        "median": statistics.median(all_latencies),
        "std_dev": statistics.stdev(all_latencies) if len(all_latencies) > 1 else 0,
        "min": min(all_latencies),
        "max": max(all_latencies),
        "p50": all_latencies_sorted[int(n * 0.50)],
        "p95": all_latencies_sorted[int(n * 0.95)],
        "p99": all_latencies_sorted[int(n * 0.99)] if n >= 100 else all_latencies_sorted[-1],
        "per_query": {}
    }

    # Per-query breakdown
    for query_text, latencies in query_latencies.items():
        metrics["per_query"][query_text[:60]] = {
            "mean": statistics.mean(latencies),
            "median": statistics.median(latencies),
            "min": min(latencies),
            "max": max(latencies),
            "std_dev": statistics.stdev(latencies) if len(latencies) > 1 else 0
        }

    return metrics


def analyze_reproducibility(results):
    """Compute reproducibility metrics - FOCUS ON RESULT CONSISTENCY"""
    metrics = {
        "result_consistency": {},
        "hit_count_stability": {},
        "dsl_consistency": {},  # Moved to end - less important
        "overall_result_consistency_pct": 0,  # PRIMARY METRIC
        "overall_dsl_consistency_pct": 0  # Secondary metric
    }

    dsl_consistent_queries = 0
    total_queries = 0
    result_similarities = []

    for query in results['queries']:
        query_text = query['query_text'][:60]
        successful_runs = [r for r in query['runs'] if r.get('success')]

        if len(successful_runs) < 2:
            continue

        total_queries += 1

        # DSL Consistency - hash the DSL and count unique hashes
        dsl_hashes = []
        for run in successful_runs:
            dsl = run.get('dsl_query', '')
            if dsl:
                dsl_hash = hashlib.md5(dsl.encode()).hexdigest()
                dsl_hashes.append(dsl_hash)

        unique_dsls = len(set(dsl_hashes))
        dsl_consistency_pct = (1 - (unique_dsls - 1) / len(dsl_hashes)) * 100 if dsl_hashes else 0

        metrics["dsl_consistency"][query_text] = {
            "unique_dsls": unique_dsls,
            "total_runs": len(dsl_hashes),
            "consistency_pct": dsl_consistency_pct
        }

        if unique_dsls == 1:
            dsl_consistent_queries += 1

        # Result Consistency - Jaccard similarity of doc IDs
        doc_id_sets = []
        hit_counts = []

        for run in successful_runs:
            doc_ids = set(hit['_id'] for hit in run.get('hits', []))
            doc_id_sets.append(doc_ids)
            hit_counts.append(run.get('total_hits', 0))

        # Average pairwise Jaccard similarity
        if len(doc_id_sets) >= 2:
            similarities = []
            for i in range(len(doc_id_sets)):
                for j in range(i + 1, len(doc_id_sets)):
                    intersection = len(doc_id_sets[i] & doc_id_sets[j])
                    union = len(doc_id_sets[i] | doc_id_sets[j])
                    jaccard = intersection / union if union > 0 else 0
                    similarities.append(jaccard)

            avg_similarity = statistics.mean(similarities) if similarities else 0
            result_similarities.append(avg_similarity)

            metrics["result_consistency"][query_text] = {
                "avg_jaccard_similarity": avg_similarity,
                "similarity_pct": avg_similarity * 100
            }

        # Hit count stability
        if hit_counts:
            metrics["hit_count_stability"][query_text] = {
                "mean": statistics.mean(hit_counts),
                "std_dev": statistics.stdev(hit_counts) if len(hit_counts) > 1 else 0,
                "min": min(hit_counts),
                "max": max(hit_counts),
                "variance_pct": (statistics.stdev(hit_counts) / statistics.mean(hit_counts) * 100) if statistics.mean(hit_counts) > 0 and len(hit_counts) > 1 else 0
            }

    # Overall metrics
    if total_queries > 0:
        metrics["overall_dsl_consistency_pct"] = (dsl_consistent_queries / total_queries) * 100

    if result_similarities:
        metrics["overall_result_consistency_pct"] = statistics.mean(result_similarities) * 100

    return metrics


def analyze_error_rates(results):
    """Compute error and reliability metrics"""
    total_runs = 0
    successful_runs = 0
    failed_runs = 0
    timeout_runs = 0
    zero_result_runs = 0
    errors_by_type = defaultdict(int)

    per_query_stats = {}

    for query in results['queries']:
        query_text = query['query_text'][:60]
        query_total = len(query['runs'])
        query_success = 0
        query_zero_results = 0

        for run in query['runs']:
            total_runs += 1

            if run.get('success'):
                successful_runs += 1
                query_success += 1

                if run.get('total_hits', 0) == 0:
                    zero_result_runs += 1
                    query_zero_results += 1
            else:
                failed_runs += 1
                error = run.get('error', 'unknown')
                errors_by_type[error] += 1

                if 'timeout' in error.lower():
                    timeout_runs += 1

        per_query_stats[query_text] = {
            "total": query_total,
            "successful": query_success,
            "success_rate_pct": (query_success / query_total) * 100,
            "zero_result_count": query_zero_results
        }

    metrics = {
        "total_runs": total_runs,
        "successful_runs": successful_runs,
        "failed_runs": failed_runs,
        "success_rate_pct": (successful_runs / total_runs) * 100 if total_runs > 0 else 0,
        "error_rate_pct": (failed_runs / total_runs) * 100 if total_runs > 0 else 0,
        "timeout_runs": timeout_runs,
        "timeout_rate_pct": (timeout_runs / total_runs) * 100 if total_runs > 0 else 0,
        "zero_result_runs": zero_result_runs,
        "zero_result_rate_pct": (zero_result_runs / successful_runs) * 100 if successful_runs > 0 else 0,
        "errors_by_type": dict(errors_by_type),
        "per_query": per_query_stats
    }

    return metrics


def prepare_llm_judging_data(results):
    """Extract data needed for LLM judging - ALL runs, including zero-hit runs"""
    judging_data = []

    for query in results['queries']:
        query_text = query['query_text']

        # Get ALL successful runs (including zero-hit runs!)
        for run_idx, run in enumerate(query['runs'], 1):
            if run.get('success'):
                total_hits = run.get('total_hits', 0)
                hits_array = run.get('hits', [])

                # Check if zero results (ONLY check total_hits, not hits array)
                # Analytics queries have total_hits but empty hits array (aggregations)
                if total_hits == 0:
                    # True zero results - mark for automatic 0 score
                    judging_data.append({
                        "query": query_text,
                        "run_number": run_idx,
                        "total_hits": 0,
                        "top_results": [],
                        "zero_results": True  # Flag for automatic 0 score
                    })
                elif not hits_array:
                    # Analytics query - has total_hits but no product hits (aggregations)
                    # Skip LLM evaluation - these need different evaluation criteria
                    judging_data.append({
                        "query": query_text,
                        "run_number": run_idx,
                        "total_hits": total_hits,
                        "top_results": [],
                        "query_type": "analytics",
                        "skip_evaluation": True  # Skip LLM evaluation for analytics
                    })
                else:
                    # Has product results - extract simplified hit data for LLM
                    simplified_hits = []
                    for hit in hits_array[:10]:  # Top 10 results
                        source = hit.get('_source', {})
                        simplified_hits.append({
                            "product_name": source.get('productDisplayName', 'Unknown'),
                            "price": source.get('price'),
                            "gender": source.get('gender'),
                            "category": source.get('masterCategory'),
                            "article_type": source.get('articleType'),
                            "color": source.get('baseColour'),
                            "season": source.get('season'),
                            "usage": source.get('usage'),
                            "rating": source.get('avgRating'),
                            "num_ratings": source.get('numRatings')
                        })

                    judging_data.append({
                        "query": query_text,
                        "run_number": run_idx,
                        "total_hits": total_hits,
                        "top_results": simplified_hits,
                        "query_type": "product_search",
                        "zero_results": False
                    })

    return judging_data


def analyze_all(pipeline_files):
    """Analyze all pipelines and generate comparison"""
    all_pipeline_metrics = {}

    for filename in pipeline_files:
        path = Path(filename)
        if not path.exists():
            print(f"⚠️  File not found: {filename}")
            continue

        results = load_results(filename)
        pipeline_name = results['pipeline']

        print(f"\n{'='*80}")
        print(f"📊 Analyzing: {pipeline_name}")
        print(f"{'='*80}")

        # Compute all metrics
        latency_metrics = analyze_latency(results)
        reproducibility_metrics = analyze_reproducibility(results)
        error_metrics = analyze_error_rates(results)
        llm_data = prepare_llm_judging_data(results)

        pipeline_metrics = {
            "pipeline": pipeline_name,
            "latency": latency_metrics,
            "reproducibility": reproducibility_metrics,
            "errors": error_metrics,
            "llm_judging_data": llm_data
        }

        all_pipeline_metrics[pipeline_name] = pipeline_metrics

        # Print summary
        print(f"\n⏱️  Latency:")
        print(f"   Mean: {latency_metrics.get('mean', 0):.1f} ms")
        print(f"   Median: {latency_metrics.get('median', 0):.1f} ms")
        print(f"   P95: {latency_metrics.get('p95', 0):.1f} ms")

        print(f"\n🔄 Reproducibility:")
        print(f"   Result Consistency: {reproducibility_metrics.get('overall_result_consistency_pct', 0):.1f}% ⭐ PRIMARY")
        print(f"   Hit Count Stability: {statistics.mean([m['variance_pct'] for m in reproducibility_metrics.get('hit_count_stability', {}).values()]) if reproducibility_metrics.get('hit_count_stability') else 0:.1f}% variance")
        print(f"   DSL Consistency: {reproducibility_metrics.get('overall_dsl_consistency_pct', 0):.1f}% (informational)")

        print(f"\n✅ Reliability:")
        print(f"   Success Rate: {error_metrics.get('success_rate_pct', 0):.1f}%")
        print(f"   Zero Result Rate: {error_metrics.get('zero_result_rate_pct', 0):.1f}%")
        print(f"   Timeout Rate: {error_metrics.get('timeout_rate_pct', 0):.1f}%")

    # Save detailed metrics
    output_file = "../analysis/metrics_analysis.json"
    with open(output_file, 'w') as f:
        json.dump(all_pipeline_metrics, f, indent=2)

    print(f"\n{'='*80}")
    print(f"✅ Analysis complete!")
    print(f"📁 Detailed metrics saved to: {output_file}")

    # Save LLM judging data separately
    llm_file = "../analysis/llm_judging_input.json"
    llm_judging_input = {
        pipeline: metrics["llm_judging_data"]
        for pipeline, metrics in all_pipeline_metrics.items()
    }
    with open(llm_file, 'w') as f:
        json.dump(llm_judging_input, f, indent=2)

    print(f"📁 LLM judging data saved to: {llm_file}")

    # Print comparison table
    print(f"\n{'='*80}")
    print("📊 COMPARISON SUMMARY - 4 Approaches")
    print(f"{'='*80}\n")

    print(f"{'Metric':<30} | {'Tools (Haiku)':<15} | {'Templates':<15} | {'Raw DSL (Haiku)':<15} | {'Raw DSL (Sonnet)':<15}")
    print(f"{'-'*30}-+-{'-'*15}-+-{'-'*15}-+-{'-'*15}-+-{'-'*15}")

    metrics_to_compare = [
        ("⭐ Result Consistency (%)", lambda m: m['reproducibility'].get('overall_result_consistency_pct', 0), ":.1f"),
        ("Avg Latency (ms)", lambda m: m['latency'].get('mean', 0), ":.1f"),
        ("Success Rate (%)", lambda m: m['errors'].get('success_rate_pct', 0), ":.1f"),
        ("Zero Result Rate (%)", lambda m: m['errors'].get('zero_result_rate_pct', 0), ":.1f"),
        ("DSL Consistency (%)", lambda m: m['reproducibility'].get('overall_dsl_consistency_pct', 0), ":.1f"),
    ]

    for metric_name, extractor, fmt in metrics_to_compare:
        values = {}
        for pipeline_name in ['tools_v1_pipe', 'templates_pipe', 'normal_pipe', 'sonnet_pipe']:
            if pipeline_name in all_pipeline_metrics:
                values[pipeline_name] = extractor(all_pipeline_metrics[pipeline_name])
            else:
                values[pipeline_name] = None

        row = f"{metric_name:<30} | "

        for idx, pipe in enumerate(['tools_v1_pipe', 'templates_pipe', 'normal_pipe', 'sonnet_pipe']):
            val = values.get(pipe)
            if isinstance(val, (int, float)):
                # Remove colon from format spec if present
                fmt_spec = fmt.lstrip(':')
                formatted = format(val, fmt_spec)
                row += f"{formatted:<10}"
            else:
                row += "N/A       "

            if idx < 4:  # Add separator except for last column
                row += " | "

        print(row)

    return all_pipeline_metrics


if __name__ == "__main__":
    # Analyze all five pipelines (FINAL - V1 tools comparison)
    pipeline_files = [
        "../results/tools_v1_pipe_results.json",
        "../results/templates_pipe_results.json",
        "../results/normal_pipe_results.json",
        "../results/sonnet_pipe_results.json"
    ]

    analyze_all(pipeline_files)
