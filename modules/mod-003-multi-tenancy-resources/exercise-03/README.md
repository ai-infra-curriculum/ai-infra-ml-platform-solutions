# Network Policy Isolation — Solution

Reference for [learning ex-03](https://github.com/ai-infra-curriculum/ai-infra-ml-platform-learning/blob/main/lessons/mod-003-multi-tenancy-resources/exercises/exercise-03-network-policy-isolation.md).

`network-policy.yaml` shows default-deny + allow-intra-team + allow monitoring + allow DNS.
Test cross-team blocking with a netshoot pod attempting to reach a service in another namespace — should time out.
