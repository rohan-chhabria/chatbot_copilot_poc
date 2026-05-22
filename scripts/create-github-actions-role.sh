#!/bin/bash
# =============================================================================
# Create GitHub Actions IAM Role for InmateCopilot
# =============================================================================
# Prerequisites:
#   - Run setup-github-actions-aws.sh first (creates OIDC + policy)
#   - Set GITHUB_ORG environment variable
#
# Usage: ./create-github-actions-role.sh
# =============================================================================

set -e

# Configuration
SERVICE_NAME="InmateCopilot"
REPO_NAME="${REPO_NAME:-ChatbotCopilot}"
GITHUB_ORG="${GITHUB_ORG:-}"

if [ -z "$GITHUB_ORG" ]; then
    echo "ERROR: GITHUB_ORG environment variable is required"
    echo ""
    echo "Usage:"
    echo "  export GITHUB_ORG=your-github-org"
    echo "  ./scripts/create-github-actions-role.sh"
    exit 1
fi

AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query "Account" --output text)
AWS_REGION=${AWS_REGION:-us-east-1}
ROLE_NAME="GitHubActions-${SERVICE_NAME}"
POLICY_NAME="GitHubActionsDeployInmateCopilot"

if [[ "$AWS_REGION" == us-gov-* ]]; then
    ARN_PREFIX="arn:aws-us-gov"
else
    ARN_PREFIX="arn:aws"
fi

POLICY_ARN="${ARN_PREFIX}:iam::${AWS_ACCOUNT_ID}:policy/${POLICY_NAME}"

echo "=============================================="
echo "Creating GitHub Actions Role"
echo "=============================================="
echo "Service:    $SERVICE_NAME"
echo "Repository: $GITHUB_ORG/$REPO_NAME"
echo "Role:       $ROLE_NAME"
echo "Region:     $AWS_REGION"
echo "=============================================="
echo ""

# Check if policy exists
if ! aws iam get-policy --policy-arn "$POLICY_ARN" &>/dev/null; then
    echo "ERROR: Policy not found: $POLICY_ARN"
    echo "Run ./scripts/setup-github-actions-aws.sh first"
    exit 1
fi

# Trust policy for GitHub OIDC
TRUST_POLICY=$(cat <<EOF
{
    "Version": "2012-10-17",
    "Statement": [{
        "Effect": "Allow",
        "Principal": {
            "Federated": "${ARN_PREFIX}:iam::${AWS_ACCOUNT_ID}:oidc-provider/token.actions.githubusercontent.com"
        },
        "Action": "sts:AssumeRoleWithWebIdentity",
        "Condition": {
            "StringEquals": {
                "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
            },
            "StringLike": {
                "token.actions.githubusercontent.com:sub": "repo:${GITHUB_ORG}/${REPO_NAME}:*"
            }
        }
    }]
}
EOF
)

# Create or update role
if aws iam get-role --role-name "$ROLE_NAME" &>/dev/null; then
    echo "Role exists — updating trust policy..."
    aws iam update-assume-role-policy \
        --role-name "$ROLE_NAME" \
        --policy-document "$TRUST_POLICY"
else
    echo "Creating new role..."
    aws iam create-role \
        --role-name "$ROLE_NAME" \
        --description "GitHub Actions deployment role for InmateCopilot chatbot" \
        --assume-role-policy-document "$TRUST_POLICY" \
        --tags Key=Service,Value="$SERVICE_NAME" Key=ManagedBy,Value=GitHubActions

    aws iam attach-role-policy \
        --role-name "$ROLE_NAME" \
        --policy-arn "$POLICY_ARN"
fi

ROLE_ARN=$(aws iam get-role --role-name "$ROLE_NAME" --query "Role.Arn" --output text)

echo ""
echo "=============================================="
echo "ROLE CREATED SUCCESSFULLY"
echo "=============================================="
echo ""
echo "Role ARN:"
echo "  $ROLE_ARN"
echo ""
echo "GitHub Setup:"
echo "=============================================="
echo ""
echo "1. Go to repository settings:"
echo "   https://github.com/${GITHUB_ORG}/${REPO_NAME}/settings/secrets/actions"
echo ""
echo "2. Add these repository secrets:"
echo ""
echo "   AWS_DEPLOY_ROLE_ARN = $ROLE_ARN"
echo "   AWS_REGION          = $AWS_REGION"
echo ""
echo "3. Create environments (Settings > Environments):"
echo "   - development"
echo "   - production (enable required reviewers)"
echo ""
echo "4. After first deploy, add API URLs:"
echo "   DEV_API_URL  = <from CloudFormation output>"
echo "   PROD_API_URL = <from CloudFormation output>"
echo ""
echo "=============================================="
