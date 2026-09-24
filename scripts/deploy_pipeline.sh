#!/usr/bin/env bash
# Create or update the CodeBuild auto-deploy stack (infra/pipeline.yaml).
#   scripts/deploy_pipeline.sh <codeconnections-arn> [true|false]   (second arg: push webhook, default true)
set -euo pipefail
cd "$(dirname "$0")/.."
REGION=${HOLDERMAP_DASHBOARD_REGION:-ap-south-1}
SITE=${HOLDERMAP_DASHBOARD_STACK:-holdermap-dashboard}
out() { aws cloudformation describe-stacks --stack-name "$SITE" --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text; }
aws cloudformation deploy --stack-name holdermap-dashboard-pipeline --region "$REGION" \
  --template-file infra/pipeline.yaml --capabilities CAPABILITY_IAM --no-fail-on-empty-changeset \
  --parameter-overrides ConnectionArn="$1" EnableWebhook="${2:-true}" SiteStack="$SITE" \
    SiteBucket="$(out BucketName)" DistributionId="$(out DistributionId)"
