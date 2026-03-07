# Knowledge Pipeline

## Positioning

The raw source of truth stays in Git-managed repositories and approved source systems.
Dify only consumes processed outputs.

The baseline Git-managed knowledge repository is `ljwx-knowledge` with:

- `content/public/**`
- `content/internal/**`
- `content/customers/{customer_id}/**`

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

## Directory and ACL Contract

- `platform/knowledge/source-registry.yaml` defines which repositories and paths are collectible.
- `platform/knowledge/taxonomy.yaml` defines the path-to-classification boundary.
- `platform/knowledge/acl-policies.yaml` defines visibility-specific `acl_expression_template` and allowed publish targets.
- `platform/contracts/knowledge-document.schema.yaml` and `platform/contracts/knowledge-chunk.schema.yaml` define the minimum manifest shape for normalize/classify/chunk outputs.

## Minimum Execution Flow

The current MVP path is:

1. ingest markdown sources from `ljwx-knowledge`
2. emit normalized document manifests
3. enrich `doc_type`, `product_area`, and `acl_expression`
4. chunk approved documents
5. publish to local dev datasets
6. invalidate or unpublish by `document_id` and republish when a rollback is needed

## Audit And Metrics

The current MVP also emits:

1. `state/<env>/events.jsonl` for lifecycle events
2. `state/<env>/audit-events.jsonl` for cross-component audit evidence
3. `state/<env>/metrics.json` for the latest publish or rollback counters
