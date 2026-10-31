# Local Docker secrets

Create these untracked files with strong, distinct values:

- `postgres_admin_password.txt`
- `postgres_migrator_password.txt`
- `postgres_api_password.txt`
- `postgres_worker_password.txt`

Only this README is tracked. Production deployments should use their platform's
secret manager rather than files stored in the repository checkout.
