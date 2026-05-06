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
- Kafka: event bus
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

## CI/CD

GitHub Actions is used only for CI and image publishing.

- `.github/workflows/ci-cd.yaml`
  - on pull requests: validates Python code and builds all container images without pushing
  - on push to `main`: validates, builds and pushes all images to GHCR

Argo CD should handle deployment by syncing this repo or a separate GitOps repo after images are published.

Published image format:

```text
ghcr.io/<github-owner>/<repo>/<service>:<tag>
```

Examples:

```text
ghcr.io/pascariucosmin93/magazon/auth-service:latest
ghcr.io/pascariucosmin93/magazon/frontend:sha-<commit>
```

### Argo CD Flow

1. GitHub Actions builds and pushes images to GHCR.
2. Helm values point to those published images.
3. Argo CD syncs the Helm chart and pulls images from GHCR into the cluster.

If you want immutable releases, point Argo CD to SHA tags instead of `latest`.

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
- PostgreSQL is not deployed by this repo; Redis and Kafka are deployed, while PostgreSQL is consumed externally.
