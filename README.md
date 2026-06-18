# microshop-platform

Microshop e-commerce platform built with FastAPI microservices, PostgreSQL, Redis, Kafka, Kubernetes and Helm.

## Services

- `auth-service`: register/login with Argon2 password hashes and JWT access tokens
- `product-service`: product catalog with stable SKUs and Redis cache
- `cart-service`: shopping cart in Redis
- `order-service`: order creation with product snapshots and order status updates
- `inventory-service`: stock reservation and inventory updates
- `payment-service`: Stripe payment/refund flow with a persistent Kafka outbox
- `notification-service`: consumes Kafka events and logs notifications
- `chat-service`: AI shopping assistant backed by Ollama
- `frontend`: storefront, dedicated product pages and a role-protected admin UI for products, users, orders, inventory and payments

## Infrastructure

- PostgreSQL: external persistent data source, configured per environment through Helm values overrides
- Redis: cart storage and product cache
- Kafka: external event bus installed separately with Helm
- Ollama: internal AI model endpoint consumed by `chat-service`
- Kubernetes manifests: raw `kubectl` deployment
- Helm chart: reusable deployment into namespace `microshop`

## Quick Start

### PostgreSQL service databases

Persistent services are configured with separate PostgreSQL databases and users:

```text
auth-service      -> microshop_auth / microshop_auth
product-service   -> microshop_product / microshop_product
order-service     -> microshop_order / microshop_order
inventory-service -> microshop_inventory / microshop_inventory
payment-service   -> microshop_payment / microshop_payment
```

Create them before deploying the Helm chart:

```sql
CREATE USER microshop_auth WITH PASSWORD '<auth-password>';
CREATE DATABASE microshop_auth OWNER microshop_auth;

CREATE USER microshop_product WITH PASSWORD '<product-password>';
CREATE DATABASE microshop_product OWNER microshop_product;

CREATE USER microshop_order WITH PASSWORD '<order-password>';
CREATE DATABASE microshop_order OWNER microshop_order;

CREATE USER microshop_inventory WITH PASSWORD '<inventory-password>';
CREATE DATABASE microshop_inventory OWNER microshop_inventory;

CREATE USER microshop_payment WITH PASSWORD '<payment-password>';
CREATE DATABASE microshop_payment OWNER microshop_payment;
```

For GitOps mode, pre-create the Kubernetes Secret with the service passwords:

```bash
kubectl create secret generic microshop-secret \
  --namespace microshop \
  --from-literal=POSTGRES_PASSWORD='<legacy-fallback-password>' \
  --from-literal=AUTH_POSTGRES_PASSWORD='<auth-password>' \
  --from-literal=PRODUCT_POSTGRES_PASSWORD='<product-password>' \
  --from-literal=ORDER_POSTGRES_PASSWORD='<order-password>' \
  --from-literal=INVENTORY_POSTGRES_PASSWORD='<inventory-password>' \
  --from-literal=PAYMENT_POSTGRES_PASSWORD='<payment-password>' \
  --from-literal=ADMIN_PASSWORD='<admin-password>' \
  --from-literal=JWT_SECRET='<jwt-secret>' \
  --from-literal=INTERNAL_API_TOKEN='<internal-token>' \
  --from-literal=STRIPE_SECRET_KEY='<stripe-secret>' \
  --from-literal=STRIPE_WEBHOOK_SECRET='<stripe-webhook-secret>'
```

`ADMIN_PASSWORD` is required by `auth-service` at startup. If the admin user already exists,
the service rotates that account to this password and stores it with Argon2.

Authentication uses Argon2 password hashes and signed JWT access tokens. Legacy SHA256
password hashes are accepted only to migrate existing users on their next successful login.

Configure Stripe to send checkout and refund events to
`https://<store-host>/api/payments/webhooks/stripe`.

`INTERNAL_API_TOKEN` should be shared between services for internal-only calls
such as the product import stock sync into `inventory-service`.

`chat-service` uses Ollama through `OLLAMA_BASE_URL`. If Ollama runs in the
`ollama` namespace as a ClusterIP service named `ollama`, use:

```text
OLLAMA_BASE_URL=http://ollama.ollama.svc.cluster.local:11434
```

### Kubernetes with Helm

```bash
./deploy.sh
```

Default deploy uses the single shared chart values file:

```text
helm/microshop/values.yaml
```

For a separate environment:

```bash
VALUES_FILE=./helm/microshop/values-test.yaml ./deploy.sh
```

This chart does not deploy Kafka. Install Kafka separately and expose it as:

```text
kafka.kafka.svc.cluster.local:9092
```

Example separate install:

```bash
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo update
kubectl create namespace kafka --dry-run=client -o yaml | kubectl apply -f -
helm upgrade --install kafka bitnami/kafka \
  --namespace kafka \
  --set listeners.client.protocol=PLAINTEXT
```

## CI/CD

GitHub Actions is used only for CI and container image publishing for Kubernetes deployments.

- `.github/workflows/test.yaml`
  - on pull requests: runs pytest, compile checks, script linting, Bandit, pip-audit, Trivy, and builds all container images without pushing
- `.github/workflows/production.yaml`
  - on push to `main`: runs the same validation and security checks, detects which deployable targets changed, creates the next Git tag in sequence (`0.0.1`, `0.0.2`, ...) only when deployable sources changed, pushes only the affected images to GHCR with that exact tag, updates the production Argo CD application and values in `pascariucosmin93/magazon-gitops`, and skips image publishing entirely for non-deployable-only changes such as `README`, tests, or GitHub workflow edits
  - on manual `workflow_dispatch`: can either run the full release flow or run only the post-deploy smoke checks by enabling the `smoke_only` input

End-to-end critical flow tests:

- start real infra locally:
  `docker compose -f tests/e2e/docker-compose.infra.yml up -d --wait`
- run the E2E suite:
  `PYTHONPATH=. pytest tests/e2e -q`
- stop and clean infra:
  `docker compose -f tests/e2e/docker-compose.infra.yml down -v --remove-orphans`
- the suite starts local `uvicorn` processes for `auth-service`, `product-service`, `cart-service`, `order-service`, `inventory-service`, and `payment-service`, then verifies:
  `auth -> cart -> order -> inventory reservation -> payment -> Stripe webhook -> order paid`

Argo CD should handle deployment by syncing the separate GitOps repo after images are published:

```text
https://github.com/pascariucosmin93/magazon-gitops
```

Published image format:

```text
ghcr.io/<github-owner>/<repo>/<service>:<tag>
```

Examples:

```text
ghcr.io/pascariucosmin93/magazon/auth-service:0.0.1
ghcr.io/pascariucosmin93/magazon/frontend:0.0.2
```

### Argo CD Flow

1. GitHub Actions builds and pushes images to GHCR.
2. GitHub Actions updates `applications/microshop-prod.yaml` and `environments/prod/values.yaml` in `pascariucosmin93/magazon-gitops`.
3. Helm values point to those published images.
4. Kafka is installed separately with Helm.
5. Argo CD syncs the Helm chart from this repo with production values from `magazon-gitops`, then pulls images from GHCR into the cluster.

The version sequence is driven by Git tags already present in the repository. The first release becomes `0.0.1`, then `0.0.2`, and so on.

Helm image values use explicit `repository` + `tag` pairs, and the production pipeline automatically pins the chart revision plus all image tags to the new release version so Argo CD deploys that exact version instead of `latest`.

### Required GitHub setup

- enable GitHub Actions for the repository
- allow `GITHUB_TOKEN` to write packages
- create `GITOPS_REPO_TOKEN` with write access to `pascariucosmin93/magazon-gitops`
- optional post-deploy smoke checks:
  - set repository variable `POST_DEPLOY_SMOKE_BASE_URL` to the public store URL, for example `http://192.168.1.8:8081`
  - set repository variable `POST_DEPLOY_SMOKE_ADMIN_EMAIL` if it differs from `admin@microshop.local`
  - set repository secret `POST_DEPLOY_SMOKE_ADMIN_PASSWORD` to also verify admin login
  - if the URL is private/LAN-only, run the workflow on a self-hosted runner that can reach it

### Kubernetes with raw manifests

```bash
./deploy.sh --manifests
```

## Kafka Topics

- `user.created`
- `order.created`
- `inventory.reserved`
- `payment.completed`
- `payment.refunded`
- `order.cancelled`
- `inventory.released`
- `notification.sent`

## Generate demo products

The seed script creates categories, generated products, and inventory through
the same admin APIs used by the frontend. It is idempotent: rerunning it skips
products that already have the generated `DEMO-*` SKU.

```bash
MAGAZON_ADMIN_PASSWORD='<admin-password>' \
python3 scripts/seed_products.py \
  --base-url http://192.168.1.8:8081 \
  --count 120 \
  --stock 50
```

Use `--dry-run` to preview the generated catalog or `--skip-inventory` when
only product records are needed.

## Admin Catalog Operations

The admin UI at `/admin.html` supports:

- single-product create/update/delete
- Excel product import with preview and apply
- Excel product export
- archived product visibility in admin
- import history for the latest applied jobs

The Excel import expects a `.xlsx` file with these columns:

```text
sku | name | description | price | category | stock | active | operation
```

Notes:

- `operation` is optional and supports `upsert` or `archive`
- when `operation` is omitted, `active=false` archives the SKU
- imports are rate-limited per client IP
- upload size is limited by `ADMIN_IMPORT_MAX_BYTES` and defaults to 2 MiB

## Notes

- The project is intentionally simple but follows realistic microservice boundaries.
- The Helm chart is ready for future GitOps adoption with Argo CD.
- PostgreSQL and Kafka are not deployed by this repo; PostgreSQL is consumed externally and Kafka should be installed separately with Helm.
- `Dockerfile` assets remain in the repository only because the CI pipeline builds and publishes container images consumed by Kubernetes.
