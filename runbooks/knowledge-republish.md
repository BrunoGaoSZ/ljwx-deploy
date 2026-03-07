# Knowledge Republish

## Use Cases

Use this runbook when processed knowledge must be republished or invalidated without changing product code.

## Triggers

1. source file deleted
2. ACL changed
3. review revoked
4. document expired
5. customer scope changed

## Steps

1. confirm source registry and publish target entries
2. rebuild normalized and chunk manifests
3. invalidate target datasets or collections
4. republish approved content
5. verify retrieval scope and sample queries

## Evidence

- publish job run ID
- invalidated dataset or collection IDs
- sample retrieval verification
