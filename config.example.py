"""
Configuration file template for Agentic Search Experiments

Copy this file to config.py and fill in your actual values.
config.py is gitignored to keep credentials safe.
"""

# OpenSearch Cluster Configuration
OPENSEARCH_URL = "https://your-cluster.region.amazonaws.com"
OPENSEARCH_USER = "admin"
OPENSEARCH_PASSWORD = "your-password"
OPENSEARCH_INDEX = "demo_amazon_fashion"

# AWS Bedrock Configuration (for LLM Judge)
# Uses default AWS credentials from environment
# Make sure you have configured:
#   - AWS_ACCESS_KEY_ID
#   - AWS_SECRET_ACCESS_KEY
#   - AWS_SESSION_TOKEN (if using temporary credentials)
AWS_REGION = "us-west-2"
BEDROCK_MODEL_ID = "us.anthropic.claude-sonnet-4-20250514-v1:0"

# Experiment Configuration
NUM_RUNS_PER_QUERY = 10
REQUEST_TIMEOUT_SECONDS = 30
