# agent-platform secrets

`secret.example.yaml` in this directory is a template manifest and must not contain real credentials.

Production practice:

1. Manage secrets via secret manager / encrypted secret workflow.
2. Inject runtime values at deploy time.
3. Do not commit concrete token/password/host values.
