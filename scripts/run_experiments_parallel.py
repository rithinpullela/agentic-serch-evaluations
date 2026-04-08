#!/usr/bin/env python3
"""
Parallel experiment runner - runs all 4 pipelines simultaneously
"""

import subprocess
import sys
from pathlib import Path

# Import configuration
try:
    from config import (
        OPENSEARCH_URL,
        OPENSEARCH_USER,
        OPENSEARCH_PASSWORD,
        OPENSEARCH_INDEX,
        NUM_RUNS_PER_QUERY,
        REQUEST_TIMEOUT_SECONDS
    )
except ImportError:
    print("❌ Error: config.py not found!")
    print("Copy config.example.py to config.py and fill in your credentials")
    sys.exit(1)

# Four pipelines for comparison
PIPELINES = [
    {"name": "tools_v1_pipe", "output": "../results/tools_v1_pipe_results.json"},
    {"name": "templates_pipe", "output": "../results/templates_pipe_results.json"},
    {"name": "normal_pipe", "output": "../results/normal_pipe_results.json"},
    {"name": "sonnet_pipe", "output": "../results/sonnet_pipe_results.json"},
]

def create_single_pipeline_script(pipeline_config):
    """Create a temporary Python script for a single pipeline"""
    script_content = f'''#!/usr/bin/env python3
import json
import time
import requests
from datetime import datetime
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URL = "{OPENSEARCH_URL}"
INDEX = "{OPENSEARCH_INDEX}"
AUTH = ("{OPENSEARCH_USER}", "{OPENSEARCH_PASSWORD}")
NUM_RUNS = {NUM_RUNS_PER_QUERY}

QUERIES = [
    "Find summer dresses for my wife's birthday party under $60",
    "Show me the cheapest premium men's watches",
    "How many different types of shoes do we have and what are their average prices?",
    "What are the top 10 most popular casual shoes for boys under $40?",
    "I need formal office wear for work presentations - men's shirts under $80"
]

PIPELINE_NAME = "{pipeline_config['name']}"
OUTPUT_FILE = "{pipeline_config['output']}"

def run_single_query(query_text, pipeline_name):
    """Execute one query and return results"""
    url = f"{{BASE_URL}}/{{INDEX}}/_search?search_pipeline={{pipeline_name}}"
    headers = {{"Content-Type": "application/json"}}
    payload = {{
        "query": {{
            "agentic": {{
                "query_text": query_text
            }}
        }}
    }}

    start_time = time.time()

    try:
        response = requests.post(
            url,
            auth=AUTH,
            headers=headers,
            json=payload,
            verify=False,
            timeout={REQUEST_TIMEOUT_SECONDS}
        )

        client_latency_ms = (time.time() - start_time) * 1000

        if response.status_code != 200:
            return {{
                "error": f"HTTP {{response.status_code}}",
                "client_latency_ms": client_latency_ms
            }}

        result = response.json()

        return {{
            "success": True,
            "server_latency_ms": result.get("took", 0),
            "client_latency_ms": client_latency_ms,
            "dsl_query": result.get("ext", {{}}).get("dsl_query", None),
            "total_hits": result.get("hits", {{}}).get("total", {{}}).get("value", 0),
            "hits": result.get("hits", {{}}).get("hits", [])
        }}

    except Exception as e:
        client_latency_ms = (time.time() - start_time) * 1000
        return {{
            "error": str(e),
            "client_latency_ms": client_latency_ms
        }}

# Main execution
print(f"🚀 [{{PIPELINE_NAME}}] Starting experiments...")

all_results = {{
    "pipeline": PIPELINE_NAME,
    "timestamp": datetime.now().isoformat(),
    "num_runs": NUM_RUNS,
    "queries": []
}}

for query_idx, query_text in enumerate(QUERIES, 1):
    print(f"[{{PIPELINE_NAME}}] Query {{query_idx}}/{{len(QUERIES)}}: \\"{{query_text[:60]}}...\\"")

    query_results = {{
        "query_text": query_text,
        "runs": []
    }}

    for run in range(1, NUM_RUNS + 1):
        result = run_single_query(query_text, PIPELINE_NAME)
        result["run_number"] = run
        result["timestamp"] = datetime.now().isoformat()

        query_results["runs"].append(result)

        # Print status
        if result.get("success"):
            latency = result.get("server_latency_ms", 0)
            hits = result.get("total_hits", 0)
            print(f"  [{{PIPELINE_NAME}}] Run {{run:2d}}/{{NUM_RUNS}} ✓ {{latency:5.0f}}ms, {{hits:3d}} hits")
        else:
            print(f"  [{{PIPELINE_NAME}}] Run {{run:2d}}/{{NUM_RUNS}} ✗ {{result.get('error', 'unknown')}}")

        time.sleep(0.5)  # Small delay between runs

    all_results["queries"].append(query_results)

# Save results
with open(OUTPUT_FILE, 'w') as f:
    json.dump(all_results, f, indent=2)

print(f"✅ [{{PIPELINE_NAME}}] Complete! Results saved to: {{OUTPUT_FILE}}")

# Summary stats
total_runs = len(QUERIES) * NUM_RUNS
successful = sum(
    1 for q in all_results["queries"]
    for r in q["runs"]
    if r.get("success")
)

print(f"📊 [{{PIPELINE_NAME}}] Summary: {{successful}}/{{total_runs}} successful")

if successful > 0:
    all_latencies = [
        r["server_latency_ms"]
        for q in all_results["queries"]
        for r in q["runs"]
        if r.get("success")
    ]
    avg_latency = sum(all_latencies) / len(all_latencies)
    print(f"📊 [{{PIPELINE_NAME}}] Avg Latency: {{avg_latency:.1f}} ms")
'''
    return script_content

def main():
    print("🎯 Parallel Agentic Search Experiment Runner")
    print(f"📊 Running {len(PIPELINES)} pipelines in parallel")
    print(f"📝 {5} queries × {NUM_RUNS_PER_QUERY} runs each = {50} requests per pipeline")
    print(f"⚡ Total: {50 * len(PIPELINES)} requests across all pipelines")
    print("=" * 80)

    # Create temporary scripts for each pipeline
    processes = []

    for pipeline in PIPELINES:
        # Create script content
        script_content = create_single_pipeline_script(pipeline)

        # Write to temp file
        temp_script = f"/tmp/run_{pipeline['name']}.py"
        with open(temp_script, 'w') as f:
            f.write(script_content)

        # Launch process
        print(f"🚀 Launching {pipeline['name']}...")
        process = subprocess.Popen(
            [sys.executable, temp_script],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        processes.append({
            "name": pipeline['name'],
            "process": process,
            "script": temp_script
        })

    print("\n" + "=" * 80)
    print("⏳ All pipelines running in parallel...")
    print("💡 This will take ~5-7 minutes (50 queries per pipeline)")
    print("=" * 80 + "\n")

    # Wait for all processes to complete and stream output
    import select

    while processes:
        for p in processes[:]:
            # Read output line by line
            line = p["process"].stdout.readline()
            if line:
                print(line.rstrip())

            # Check if process finished
            if p["process"].poll() is not None:
                # Read any remaining output
                remaining = p["process"].stdout.read()
                if remaining:
                    print(remaining.rstrip())

                print(f"\n✅ {p['name']} finished!\n")
                processes.remove(p)

        time.sleep(0.1)

    print("\n" + "=" * 80)
    print("🎉 All experiments complete!")
    print("\n📁 Results files:")
    for pipeline in PIPELINES:
        output_path = Path(pipeline['output'])
        if output_path.exists():
            size_kb = output_path.stat().st_size / 1024
            print(f"   - {pipeline['output']} ({size_kb:.1f} KB)")

    print("\n📊 Next steps:")
    print("   1. python3 analyze_metrics.py")
    print("   2. python3 llm_judge_async_new.py")

if __name__ == "__main__":
    import time
    main()
