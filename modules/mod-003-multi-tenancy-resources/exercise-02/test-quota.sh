#!/usr/bin/env bash
# Verify ResourceQuota enforcement.
set -e
NS=${NS:-team-a}

echo "Test 1: pod exceeding quota should be rejected"
kubectl apply -f - <<EOF
apiVersion: v1
kind: Pod
metadata: { name: too-big, namespace: $NS }
spec:
  containers: [{ name: c, image: nginx, resources: { requests: { cpu: "10" } } }]
EOF
# Expect this to fail at admission

echo "Test 2: 5 pods at cpu=1 should fill quota; 6th rejected"
for i in 1 2 3 4 5 6; do
  kubectl run pod-$i --image=nginx -n $NS \
    --requests="cpu=1" --restart=Never || echo "pod-$i rejected (expected for #5+)"
done
