#!/usr/bin/env bash
# Publish the static dashboard (dashboard/site) to its own stack. Prints the access link.
#   scripts/deploy_dashboard.sh            upload (creates the stack the first time, ~5 min)
#   scripts/deploy_dashboard.sh --rotate   new access key: old links stop working
set -euo pipefail
cd "$(dirname "$0")/.."
STACK=${HOLDERMAP_DASHBOARD_STACK:-holdermap-dashboard}
REGION=${HOLDERMAP_DASHBOARD_REGION:-ap-south-1}
SITE=dashboard/site
KEYFILE=data/dashboard/access_key                    # gitignored; the only copy of the key
command -v aws >/dev/null 2>&1 || { echo "error: aws CLI not found (install it and run 'aws configure')" >&2; exit 1; }
[ -f "$SITE/index.html" ] || { echo "error: $SITE/index.html is missing; nothing to publish" >&2; exit 1; }
mkdir -p data/dashboard
if [ "${1:-}" = "--rotate" ] || [ ! -s "$KEYFILE" ]; then
  python3 -c "import secrets; print(secrets.token_urlsafe(18))" > "$KEYFILE"
  chmod 600 "$KEYFILE"
fi
KEY=$(tr -d '\n' < "$KEYFILE")
HASH=$(printf %s "$KEY" | shasum -a 256 | cut -d' ' -f1)
sed "s/__KEY_HASH__/$HASH/" infra/dashboard.yaml > data/dashboard/rendered.yaml
aws cloudformation deploy --stack-name "$STACK" --region "$REGION" \
  --template-file data/dashboard/rendered.yaml --no-fail-on-empty-changeset >/dev/null
out() { aws cloudformation describe-stacks --stack-name "$STACK" --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text; }
BUCKET=$(out BucketName); DIST=$(out DistributionId); URL=$(out Url)
PY=python3; [ -x .venv/bin/python ] && PY=.venv/bin/python
if [ -f scripts/refresh_dashboard_prices.py ]; then
  "$PY" scripts/refresh_dashboard_prices.py \
    || echo "warning: price refresh failed; publishing the existing data.js" >&2
fi
aws s3 sync "$SITE" "s3://$BUCKET/" --delete --cache-control "no-cache" --only-show-errors
aws cloudfront create-invalidation --distribution-id "$DIST" --paths "/*" >/dev/null
echo "$URL/?key=$KEY" > data/dashboard/link.txt
echo "dashboard: $URL/?key=$KEY"
