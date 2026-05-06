# microshop-platform

Microshop e-commerce platform built with FastAPI microservices, PostgreSQL, Redis, Kafka, Docker, Kubernetes and Helm.

## Services

- `auth-service`: register/login and token cache in Redis
- `product-service`: product catalog and Redis cache
- `cart-service`: shopping cart in Redis
- `order-service`: order creation and order status updates
- `inventory-service`: stock reservation and inventory updates
- `payment-service`: simulated payment flow
- `notification-service`: consumes Kafka events and logs notifications
- `frontend`: static UI for demo flows

## Infrastructure

- PostgreSQL: external persistent data source at `192.168.1.16`
- Redis: cart storage, product cache, token cache
- Kafka: external event bus installed separately with Helm
- Docker Compose: local development stack
- Kubernetes manifests: raw `kubectl` deployment
- Helm chart: reusable deployment into namespace `microshop`

## Quick Start

### Local

```bash
docker compose up --build
```

Frontend: `http://localhost:8080`

Note: local startup expects PostgreSQL to already be reachable at `192.168.1.16:5432`.

### Kubernetes with Helm

```bash
./deploy.sh
```

This chart does not deploy Kafka. Install Kafka separately and expose it as:

```text
kafka-broker-0.kafka-broker-headless.kafka.svc.cluster.local:9092
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

GitHub Actions is used only for CI and image publishing.

- `.github/workflows/ci-cd.yaml`
  - on pull requests: validates Python code and builds all container images without pushing
  - on push to `main`: creates the next Git tag in sequence (`0.0.1`, `0.0.2`, ...), updates `helm/microshop/values.yaml` to that version, and pushes all images to GHCR with that exact tag

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
