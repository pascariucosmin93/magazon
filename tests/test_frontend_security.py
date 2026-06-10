import base64
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UI_MODULE = ROOT / "frontend/public/assets/js/shared/ui.js"


def test_escape_html_neutralizes_xss_payloads():
    encoded_module = base64.b64encode(UI_MODULE.read_bytes()).decode("ascii")
    script = f"""
      const module = await import("data:text/javascript;base64,{encoded_module}");
      const payload = `<img src=x onerror="globalThis.pwned=true">'&`;
      const escaped = module.escapeHtml(payload);
      if (escaped !== "&lt;img src=x onerror=&quot;globalThis.pwned=true&quot;&gt;&#39;&amp;") {{
        throw new Error(`Unexpected escaped value: ${{escaped}}`);
      }}
    """
    subprocess.run(
        ["node", "--input-type=module", "--eval", script],
        check=True,
        cwd=ROOT,
    )


def test_dynamic_frontend_renderers_use_html_escaping():
    protected_files = [
        "frontend/public/assets/js/storefront/catalog.js",
        "frontend/public/assets/js/storefront/cart.js",
        "frontend/public/assets/js/storefront/orders.js",
        "frontend/public/assets/js/storefront/account.js",
        "frontend/public/assets/js/checkout-page.js",
        "frontend/public/assets/js/payment.js",
        "frontend/public/assets/js/order-page.js",
    ]
    for relative_path in protected_files:
        source = (ROOT / relative_path).read_text()
        assert "escapeHtml" in source, f"{relative_path} must escape dynamic HTML"

    combined = "\n".join((ROOT / path).read_text() for path in protected_files)
    unsafe_html_fragments = [
        "<h3 class=\"product-name\">${product.name}</h3>",
        "<p class=\"product-description\">${product.description}</p>",
        "<strong>${item.name}</strong>",
        "<strong>${address.label}",
        "<span>${address.recipient_name}",
        "<strong>${delivery.customer_name}</strong>",
        "<strong>${delivery.customer_email}</strong>",
        "<strong>${delivery.shipping_address}</strong>",
        "<strong>${order.customer_name",
        "<strong>${order.customer_email",
        "<strong>${order.shipping_address",
        "<strong>${order.cancellation_reason}</strong>",
    ]
    for fragment in unsafe_html_fragments:
        assert fragment not in combined
