#!/bin/bash
# =============================================================================
# Create GitHub Actions IAM Role for InmateCopilot
# =============================================================================
# Usage: ./create-github-actions-role.sh <service-name> <github-repo-name>
# Example: ./create-github-actions-role.sh InmateCopilot chatbot_copilot_poc
# =============================================================================

set -e

SERVICE_NAME=$1
REPO_NAME=$2

if [ -z "$SERVICE_NAME" ] || [ -z "$REPO_NAME" ]; then
    echo "Usage: $0 <service-name> <github-repo-name>"
    echo "Example: $0 InmateCopilot chatbot_copilot_poc"
    exit 1
fi

AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query "Account" --output text)
AWS_REGION=${AWS_REGION:-us-east-1}
GITHUB_ORG=${GITHUB_ORG:-"YOUR_GITHUB_ORG"}
ROLE_NAME="GitHubActions-${SERVICE_NAME}"

if [[ "$AWS_REGION" == us-gov-* ]]; then
    ARN_PREFIX="arn:aws-us-gov"
    echo "GovCloud detected (region: $AWS_REGION)"
else
    ARN_PREFIX="arn:aws"
fi

echo "=============================================="
echo "Creating GitHub Actions Role — InmateCopilot"
echo "=============================================="
echo "Service:    $SERVICE_NAME"
echo "Repository: $GITHUB_ORG/$REPO_NAME"
echo "Role Name:  $ROLE_NAME"
echo "Region:     $AWS_REGION"
echo "=============================================="
echo ""

TRUST_POLICY="{
    \"Version\": \"2012-10-17\",
    \"Statement\": [{
        \"Effect\": \"Allow\",
        \"Principal\": {
            \"Federated\": \"${ARN_PREFIX}:iam::${AWS_ACCOUNT_ID}:oidc-provider/token.actions.githubusercontent.com\"
        },
        \"Action\": \"sts:AssumeRoleWithWebIdentity\",
        \"Condition\": {
            \"StringEquals\": {
                \"token.actions.githubusercontent.com:aud\": \"sts.amazonaws.com\"
            },
            \"StringLike\": {
                \"token.actions.githubusercontent.com:sub\": \"repo:${GITHUB_ORG}/${REPO_NAME}:*\"
            }
        }
    }]
}"

if aws iam get-role --role-name "$ROLE_NAME" &>/dev/null; then
    echo "Role exists — updating trust policy..."
    aws iam update-assume-role-policy --role-name "$ROLE_NAME" --policy-document "$TRUST_POLICY"
    echo "Trust policy updated"
else
    echo "Creating new role..."
    aws iam create-role \
        --role-name "$ROLE_NAME" \
        --description "GitHub Actions deployment role for ${SERVICE_NAME} (InmateCopilot chatbot)" \
        --assume-role-policy-document "$TRUST_POLICY" \
        --tags Key=Service,Value="$SERVICE_NAME" Key=ManagedBy,Value=GitHubActions

    aws iam attach-role-policy \
        --role-name "$ROLE_NAME" \
        --policy-arn "${ARN_PREFIX}:iam::${AWS_ACCOUNT_ID}:policy/GitHubActionsDeployBase"

    echo "Role created and policy attached"
fi

ROLE_ARN=$(aws iam get-role --role-name "$ROLE_NAME" --query "Role.Arn" --output text)

echo ""
echo "=============================================="
echo "SETUP COMPLETE"
echo "=============================================="
echo ""
echo "Role ARN (add to GitHub Environment secrets):"
echo ""
echo "  $ROLE_ARN"
echo ""
echo "GitHub Setup:"
echo "  1. Go to: https://github.com/${GITHUB_ORG}/${REPO_NAME}/settings/environments"
echo "  2. Create environments: dev, staging, prod"
echo "  3. Add secrets to each environment:"
echo "       AWS_DEPLOY_ROLE_ARN = $ROLE_ARN"
echo "       DEPLOYMENT_ID       = <10-char ID from first deploy setup>"
echo "  4. Enable required reviewers on staging and prod"
echo ""
echo "Stack names deployed by CI/CD:"
echo "  - InmateCopilot-V1-dev"
echo "  - InmateCopilot-V1-staging"
echo "  - InmateCopilot-V1-prod"
echo ""
echo "=============================================="
