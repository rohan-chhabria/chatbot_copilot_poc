#!/bin/bash
# =============================================================================
# One-Time AWS Setup for GitHub Actions — InmateCopilot
# =============================================================================
# Run this ONCE per AWS account to set up:
#   1. OIDC Provider for GitHub Actions
#   2. Base Deployment Policy (SAM/Lambda/CloudFormation permissions)
#
# After this, use create-github-actions-role.sh for each repository.
# =============================================================================

set -e

echo "=============================================="
echo "GitHub Actions AWS Setup — InmateCopilot"
echo "=============================================="
echo ""

AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query "Account" --output text)
AWS_REGION=${AWS_REGION:-us-east-1}

if [[ "$AWS_REGION" == us-gov-* ]]; then
    ARN_PREFIX="arn:aws-us-gov"
    echo "GovCloud detected"
else
    ARN_PREFIX="arn:aws"
fi

echo "AWS Account: $AWS_ACCOUNT_ID"
echo "AWS Region:  $AWS_REGION"
echo "ARN Prefix:  $ARN_PREFIX"
echo ""

# -----------------------------------------------------------------------------
# Step 1: Create OIDC Provider
# -----------------------------------------------------------------------------
echo "Step 1: Creating OIDC Provider..."

OIDC_EXISTS=$(aws iam list-open-id-connect-providers --query "OpenIDConnectProviderList[?contains(Arn, 'token.actions.githubusercontent.com')].Arn" --output text)

if [ -n "$OIDC_EXISTS" ]; then
    echo "  OIDC Provider already exists: $OIDC_EXISTS"
else
    aws iam create-open-id-connect-provider \
        --url https://token.actions.githubusercontent.com \
        --client-id-list sts.amazonaws.com \
        --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1 \
        --tags Key=Purpose,Value=GitHubActions Key=ManagedBy,Value=Platform Key=Service,Value=InmateCopilot
    echo "  OIDC Provider created"
fi

# -----------------------------------------------------------------------------
# Step 2: Create Base Deployment Policy (SAM zip deploy — no ECR/ECS)
# -----------------------------------------------------------------------------
echo ""
echo "Step 2: Creating Base Deployment Policy..."

POLICY_ARN="${ARN_PREFIX}:iam::${AWS_ACCOUNT_ID}:policy/GitHubActionsDeployBase"

POLICY_DOC='{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "S3ForSAMArtifacts",
      "Effect": "Allow",
      "Action": "s3:*",
      "Resource": "*"
    },
    {
      "Sid": "DynamoDBFull",
      "Effect": "Allow",
      "Action": "dynamodb:*",
      "Resource": "*"
    },
    {
      "Sid": "LambdaFull",
      "Effect": "Allow",
      "Action": "lambda:*",
      "Resource": "*"
    },
    {
      "Sid": "APIGatewayFull",
      "Effect": "Allow",
      "Action": "apigateway:*",
      "Resource": "*"
    },
    {
      "Sid": "CloudFormationFull",
      "Effect": "Allow",
      "Action": "cloudformation:*",
      "Resource": "*"
    },
    {
      "Sid": "CloudWatchAlarms",
      "Effect": "Allow",
      "Action": [
        "cloudwatch:PutMetricAlarm",
        "cloudwatch:DeleteAlarms",
        "cloudwatch:DescribeAlarms"
      ],
      "Resource": "*"
    },
    {
      "Sid": "LogsFull",
      "Effect": "Allow",
      "Action": "logs:*",
      "Resource": "*"
    },
    {
      "Sid": "IAMForServiceRoles",
      "Effect": "Allow",
      "Action": [
        "iam:GetRole",
        "iam:CreateRole",
        "iam:DeleteRole",
        "iam:AttachRolePolicy",
        "iam:DetachRolePolicy",
        "iam:PutRolePolicy",
        "iam:DeleteRolePolicy",
        "iam:PassRole",
        "iam:TagRole",
        "iam:UntagRole",
        "iam:GetRolePolicy",
        "iam:ListRolePolicies",
        "iam:ListAttachedRolePolicies",
        "iam:CreateServiceLinkedRole"
      ],
      "Resource": "*"
    },
    {
      "Sid": "SecretsManagerRead",
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue",
        "secretsmanager:DescribeSecret"
      ],
      "Resource": "*"
    }
  ]
}'

if aws iam get-policy --policy-arn "$POLICY_ARN" &>/dev/null; then
    echo "  Policy exists — updating to latest version..."

    aws iam create-policy-version \
        --policy-arn "$POLICY_ARN" \
        --policy-document "$POLICY_DOC" \
        --set-as-default

    OLD_VERSIONS=$(aws iam list-policy-versions --policy-arn "$POLICY_ARN" --query "Versions[?IsDefaultVersion==\`false\`].VersionId" --output text)
    for VERSION in $OLD_VERSIONS; do
        aws iam delete-policy-version --policy-arn "$POLICY_ARN" --version-id "$VERSION" 2>/dev/null || true
    done

    echo "  Policy updated"
else
    aws iam create-policy \
        --policy-name GitHubActionsDeployBase \
        --description "SAM deployment permissions for GitHub Actions (InmateCopilot)" \
        --policy-document "$POLICY_DOC"
    echo "  Policy created"
fi

# -----------------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------------
echo ""
echo "=============================================="
echo "AWS SETUP COMPLETE"
echo "=============================================="
echo ""
echo "Created:"
echo "  - OIDC Provider: token.actions.githubusercontent.com"
echo "  - Policy: GitHubActionsDeployBase"
echo ""
echo "Next Steps:"
echo "  1. Set your GitHub org: export GITHUB_ORG=your-org-name"
echo "  2. Create role for InmateCopilot:"
echo "     ./scripts/create-github-actions-role.sh InmateCopilot chatbot_copilot_poc"
echo "  3. Add AWS_DEPLOY_ROLE_ARN and DEPLOYMENT_ID to GitHub Environments:"
echo "     dev, staging, prod"
echo ""
echo "=============================================="
