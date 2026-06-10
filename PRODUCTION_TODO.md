# Production follow-up

Priorities remaining after the stored XSS fix:

1. Restrict Stripe `return_base_url` to the configured public Cloudflare domain.
2. Configure and test automated PostgreSQL backups, retention, and restore.
3. Verify Cloudflare forwards `X-Forwarded-Proto: https` so auth cookies are `Secure`.
4. Run at least two replicas for frontend, auth, product, order, and payment.
5. Add post-deploy smoke tests and automatic rollback on failed readiness or checkout.
6. Add alerts for HTTP 5xx, unavailable pods, PostgreSQL, Kafka, and payment failures.
