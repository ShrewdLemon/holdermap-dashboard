#!/usr/bin/env bash
# Create or update the site stack (S3 + CloudFront + access-link gate), then publish.
# Only needed for infra changes or a new access key; everyday deploys are scripts/deploy.sh (CI runs it).
#   scripts/deploy_infra.sh            create/update the stack (~5 min the first time)
#   scripts/deploy_infra.sh --rotate   new access key: old links stop working
set -euo pipefail
cd "$(dirname "$0")/.."
STACK=${HOLDERMAP_DASHBOARD_STACK:-holdermap-dashboard}
REGION=${HOLDERMAP_DASHBOARD_REGION:-ap-south-1}
KEYFILE=.local/access_key                    # gitignored; the only copy of the key
mkdir -p .local
if [ "${1:-}" = "--rotate" ] || [ ! -s "$KEYFILE" ]; then
  python3 -c "import secrets; print(secrets.token_urlsafe(18))" > "$KEYFILE"
  chmod 600 "$KEYFILE"
fi
KEY=$(tr -d '\n' < "$KEYFILE")
HASH=$(printf %s "$KEY" | shasum -a 256 | cut -d' ' -f1)
sed "s/__KEY_HASH__/$HASH/" infra/dashboard.yaml > .local/rendered.yaml
aws cloudformation deploy --stack-name "$STACK" --region "$REGION" \
  --template-file .local/rendered.yaml --no-fail-on-empty-changeset >/dev/null
scripts/deploy.sh
URL=$(aws cloudformation describe-stacks --stack-name "$STACK" --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='Url'].OutputValue" --output text)
echo "$URL/?key=$KEY" > .local/link.txt
echo "dashboard: $URL/?key=$KEY"
