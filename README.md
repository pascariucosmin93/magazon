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

- PostgreSQL: persistent data
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

### Kubernetes with Helm

```bash
./deploy.sh
```

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
