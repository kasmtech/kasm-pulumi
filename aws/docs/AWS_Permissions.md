# Required IAM User Permissions

- PowerUserAccess: Provides full access to AWS services and resources, but does not allow management of Users and groups. See AWS [docs](https://docs.aws.amazon.com/aws-managed-policy/latest/reference/PowerUserAccess.html) for permission details.
- Inline IAM Permission
  - Creates an IAM role with an assume role policy.
  - Creates an instance profile and associates it with the role.
  - Additional IAM related permissions required for creating an EKS cluster

```bash
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "iam:GetRole",
                "iam:ListRolePolicies",
                "iam:ListAttachedRolePolicies",
                "iam:AttachRolePolicy",
                "iam:GetInstanceProfile",
                "iam:CreateRole",
                "iam:PutRolePolicy",
                "iam:CreateInstanceProfile",
                "iam:ListInstanceProfilesForRole",
                "iam:AddRoleToInstanceProfile"
                
            ],
            "Resource": "*"
        },
        {
            "Effect": "Allow",
            "Action": [
                       "iam:PassRole",
                       "iam:DeleteRole",
                       "iam:DeleteInstanceProfile",
                       "iam:RemoveRoleFromInstanceProfile",
                       "iam:DetachRolePolicy"
            ],
            "Resource": [
                "arn:aws:iam::*:role/*kasm-eks-cluster-*",
                "arn:aws:iam::*:role/*kasm-default-autoscaler-ec2-role*",
                "arn:aws:iam::*:instance-profile/*kasm-default-autoscaler-ec2-profile*",
                "arn:aws:iam::*:instance-profile/*kasm-eks-cluster-*",
                "arn:aws:iam::*:role/*kasm-eks-cluster-*"
            ]
        }
    ]
}
```