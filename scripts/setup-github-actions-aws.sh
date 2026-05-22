#!/bin/bash
# =============================================================================
# One-Time AWS Setup for GitHub Actions — InmateCopilot (ECS Fargate)
# =============================================================================
# Run this ONCE per AWS account to set up:
#   1. OIDC Provider for GitHub Actions
#   2. Deployment Policy (ECS, ECR, ElastiCache, DynamoDB, CloudFormation)
#
# After this, use create-github-actions-role.sh for the repository.
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
echo ""

# -----------------------------------------------------------------------------
# Step 1: Create OIDC Provider (if not exists)
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
        --tags Key=Purpose,Value=GitHubActions Key=Service,Value=InmateCopilot
    echo "  OIDC Provider created"
fi

# -----------------------------------------------------------------------------
# Step 2: Create Deployment Policy (ECS Fargate + SAM)
# -----------------------------------------------------------------------------
echo ""
echo "Step 2: Creating Deployment Policy..."

POLICY_NAME="GitHubActionsDeployInmateCopilot"
POLICY_ARN="${ARN_PREFIX}:iam::${AWS_ACCOUNT_ID}:policy/${POLICY_NAME}"

POLICY_DOC='{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ECRFullAccess",
      "Effect": "Allow",
      "Action": [
        "ecr:GetAuthorizationToken",
        "ecr:BatchCheckLayerAvailability",
        "ecr:GetDownloadUrlForLayer",
        "ecr:BatchGetImage",
        "ecr:PutImage",
        "ecr:InitiateLayerUpload",
        "ecr:UploadLayerPart",
        "ecr:CompleteLayerUpload",
        "ecr:CreateRepository",
        "ecr:DescribeRepositories",
        "ecr:DeleteRepository",
        "ecr:PutLifecyclePolicy",
        "ecr:SetRepositoryPolicy",
        "ecr:PutImageScanningConfiguration",
        "ecr:TagResource"
      ],
      "Resource": "*"
    },
    {
      "Sid": "ECSFullAccess",
      "Effect": "Allow",
      "Action": [
        "ecs:*"
      ],
      "Resource": "*"
    },
    {
      "Sid": "ElastiCacheFullAccess",
      "Effect": "Allow",
      "Action": [
        "elasticache:*"
      ],
      "Resource": "*"
    },
    {
      "Sid": "EC2ForVPCAndSG",
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeVpcs",
        "ec2:DescribeSubnets",
        "ec2:DescribeSecurityGroups",
        "ec2:DescribeNetworkInterfaces",
        "ec2:CreateSecurityGroup",
        "ec2:DeleteSecurityGroup",
        "ec2:AuthorizeSecurityGroupIngress",
        "ec2:AuthorizeSecurityGroupEgress",
        "ec2:RevokeSecurityGroupIngress",
        "ec2:RevokeSecurityGroupEgress",
        "ec2:CreateTags",
        "ec2:DeleteTags"
      ],
      "Resource": "*"
    },
    {
      "Sid": "ELBFullAccess",
      "Effect": "Allow",
      "Action": [
        "elasticloadbalancing:*"
      ],
      "Resource": "*"
    },
    {
      "Sid": "DynamoDBFullAccess",
      "Effect": "Allow",
      "Action": [
        "dynamodb:*"
      ],
      "Resource": "*"
    },
    {
      "Sid": "CloudFormationFullAccess",
      "Effect": "Allow",
      "Action": [
        "cloudformation:*"
      ],
      "Resource": "*"
    },
    {
      "Sid": "S3ForSAMArtifacts",
      "Effect": "Allow",
      "Action": [
        "s3:*"
      ],
      "Resource": "*"
    },
    {
      "Sid": "CloudWatchLogs",
      "Effect": "Allow",
      "Action": [
        "logs:*"
      ],
      "Resource": "*"
    },
    {
      "Sid": "CloudWatchAlarms",
      "Effect": "Allow",
      "Action": [
        "cloudwatch:*"
      ],
      "Resource": "*"
    },
    {
      "Sid": "ApplicationAutoScaling",
      "Effect": "Allow",
      "Action": [
        "application-autoscaling:*"
      ],
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
    }
  ]
}'

if aws iam get-policy --policy-arn "$POLICY_ARN" &>/dev/null; then
    echo "  Policy exists — updating to latest version..."
    
    aws iam create-policy-version \
        --policy-arn "$POLICY_ARN" \
        --policy-document "$POLICY_DOC" \
        --set-as-default
    
    # Clean up old versions (keep only default)
    OLD_VERSIONS=$(aws iam list-policy-versions --policy-arn "$POLICY_ARN" --query "Versions[?IsDefaultVersion==\`false\`].VersionId" --output text)
    for VERSION in $OLD_VERSIONS; do
        aws iam delete-policy-version --policy-arn "$POLICY_ARN" --version-id "$VERSION" 2>/dev/null || true
    done
    
    echo "  Policy updated"
else
    aws iam create-policy \
        --policy-name "$POLICY_NAME" \
        --description "ECS Fargate deployment permissions for InmateCopilot" \
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
echo "  - Policy: $POLICY_NAME"
echo ""
echo "Next Step:"
echo "  Create the GitHub Actions role:"
echo ""
echo "    export GITHUB_ORG=your-github-org"
echo "    ./scripts/create-github-actions-role.sh"
echo ""
echo "=============================================="
