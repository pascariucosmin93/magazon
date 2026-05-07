# microshop-platform

Microshop e-commerce platform built with FastAPI microservices, PostgreSQL, Redis, Kafka, Kubernetes and Helm.

## Services

- `auth-service`: register/login with Argon2 password hashes and JWT access tokens
- `product-service`: product catalog and Redis cache
- `cart-service`: shopping cart in Redis
- `order-service`: order creation and order status updates
- `inventory-service`: stock reservation and inventory updates
- `payment-service`: simulated payment flow
- `notification-service`: consumes Kafka events and logs notifications
- `frontend`: static UI for demo flows

## Infrastructure

- PostgreSQL: external persistent data source at `192.168.1.16`, with one database/user per persistent service
- Redis: cart storage and product cache
- Kafka: external event bus installed separately with Helm
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
  --from-literal=JWT_SECRET='<jwt-secret>'
```

`ADMIN_PASSWORD` is required by `auth-service` at startup. If the admin user already exists,
the service rotates that account to this password and stores it with Argon2.

Authentication uses Argon2 password hashes and signed JWT access tokens. Legacy SHA256
password hashes are accepted only to migrate existing users on their next successful login.

### Kubernetes with Helm

```bash
./deploy.sh
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

- `.github/workflows/ci-cd.yaml`
  - on pull requests: runs pytest, compile checks, script linting, Bandit, pip-audit, Trivy, OWASP Dependency-Check, and builds all container images without pushing
  - on push to `main`: runs the same validation and security checks, creates the next Git tag in sequence (`0.0.1`, `0.0.2`, ...), updates `helm/microshop/values.yaml` to that version, and pushes all images to GHCR with that exact tag

Argo CD should handle deployment by syncing this repo or a separate GitOps repo after images are published.

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
2. Helm values point to those published images.
3. Kafka is installed separately with Helm.
4. Argo CD syncs the Helm chart and pulls images from GHCR into the cluster.

The version sequence is driven by Git tags already present in the repository. The first release becomes `0.0.1`, then `0.0.2`, and so on.

Helm image values use explicit `repository` + `tag` pairs, and the CI pipeline automatically bumps all image tags in `helm/microshop/values.yaml` to the new release version so Argo CD deploys that exact version instead of `latest`.

### Required GitHub setup

- enable GitHub Actions for the repository
- allow `GITHUB_TOKEN` to write packages

### Kubernetes with raw manifests

```bash
./deploy.sh --manifests
```

## Kafka Topics

- `user.created`
- `order.created`
- `inventory.reserved`
- `payment.completed`
- `notification.sent`

## Notes

- The project is intentionally simple but follows realistic microservice boundaries.
- The Helm chart is ready for future GitOps adoption with Argo CD.
- PostgreSQL and Kafka are not deployed by this repo; PostgreSQL is consumed externally and Kafka should be installed separately with Helm.
- `Dockerfile` assets remain in the repository only because the CI pipeline builds and publishes container images consumed by Kubernetes.
