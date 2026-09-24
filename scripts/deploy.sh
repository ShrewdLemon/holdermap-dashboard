#!/usr/bin/env bash
# Build and publish the dashboard: latest NSE prices -> build -> S3 -> CloudFront.
# CodeBuild runs this on every push to main and every trading evening; it also works locally.
#   scripts/deploy.sh             fetch prices, build, upload
#   scripts/deploy.sh --offline   no NSE requests (cached prices only)
set -euo pipefail
cd "$(dirname "$0")/.."
STACK=${HOLDERMAP_DASHBOARD_STACK:-holdermap-dashboard}
REGION=${HOLDERMAP_DASHBOARD_REGION:-ap-south-1}
out() { aws cloudformation describe-stacks --stack-name "$STACK" --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text; }
BUCKET=$(out BucketName); DIST=$(out DistributionId); URL=$(out Url)
STATE="s3://$BUCKET/_state/closes.json"   # the price cache, kept between builds
mkdir -p cache
aws s3 cp "$STATE" cache/closes.json --only-show-errors 2>/dev/null || echo "no price cache yet; starting fresh"
python3 pipeline/live.py "$@"
python3 build.py
if command -v node >/dev/null; then node --check dashboard/site/app.js; fi
aws s3 cp cache/closes.json "$STATE" --only-show-errors
aws s3 sync dashboard/site "s3://$BUCKET/" --delete --exclude "_state/*" --cache-control "no-cache" --only-show-errors
aws cloudfront create-invalidation --distribution-id "$DIST" --paths "/*" --query Invalidation.Id --output text >/dev/null
echo "published $URL ($(git rev-parse --short HEAD 2>/dev/null || echo local))"
