# Knowledge Pipeline

## Positioning

The raw source of truth stays in Git-managed repositories and approved source systems.
Dify only consumes processed outputs.

## Pipeline

1. collect
2. normalize
3. classify
4. deduplicate
5. chunk
6. tag
7. apply ACL
8. review
9. publish
10. invalidate or unpublish

## Publish Targets

- Dify datasets for product-facing retrieval
- internal retrieval collections for platform and support use cases
- customer-scoped retrieval collections when tenant isolation is required

## Invalidate Triggers

Publishing is not append-only. A document or chunk must be invalidated when:

1. source content is deleted
2. ACL changes
3. `review_status` moves out of `approved`
4. `expires_at` is reached
5. customer scope changes

The target configuration lives in `platform/knowledge/publish-targets.yaml`.
