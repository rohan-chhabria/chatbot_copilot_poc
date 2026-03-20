"""Tests for tenant_router module."""

from __future__ import annotations

import pytest

from src.tenant.tenant_router import TenantNotFoundError, list_tenants, resolve_tenant


class TestResolveTenant:
    def test_resolve_known_tenant(self):
        tenant = resolve_tenant("demo")
        assert tenant.customer_key == "demo"
        assert tenant.db_name is not None

    def test_resolve_normalizes_case(self):
        tenant = resolve_tenant("DEMO")
        assert tenant.customer_key == "demo"

    def test_resolve_normalizes_whitespace(self):
        tenant = resolve_tenant("  demo  ")
        assert tenant.customer_key == "demo"

    def test_empty_customer_key_raises(self):
        with pytest.raises(TenantNotFoundError, match="required"):
            resolve_tenant("")

    def test_none_customer_key_raises(self):
        with pytest.raises(TenantNotFoundError):
            resolve_tenant(None)


class TestStrictValidation:
    def test_strict_mode_rejects_unknown(self, monkeypatch):
        monkeypatch.setattr("src.tenant.tenant_router.STRICT_TENANT_VALIDATION", True)
        monkeypatch.setattr(
            "src.shared.config.STRICT_TENANT_VALIDATION", True
        )
        with pytest.raises(TenantNotFoundError, match="Unknown tenant"):
            resolve_tenant("nonexistent_tenant")

    def test_non_strict_allows_unknown(self, monkeypatch):
        monkeypatch.setattr("src.tenant.tenant_router.STRICT_TENANT_VALIDATION", False)
        tenant = resolve_tenant("unknown_but_ok")
        assert tenant is not None


class TestListTenants:
    def test_list_returns_keys(self):
        tenants = list_tenants()
        assert isinstance(tenants, list)
        assert "demo" in tenants
