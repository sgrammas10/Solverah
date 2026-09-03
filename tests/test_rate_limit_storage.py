"""Tests for rate-limit storage resolution.

Regression cover for a real inconsistency: `Settings` resolved rate-limit storage
from REDIS_URL, but `init_rate_limiter` read only RATELIMIT_STORAGE_URI. Setting
REDIS_URL therefore configured the cache while leaving the limiter on per-worker
memory counters -- with the config layer reporting "redis" and the limiter
warning "memory", disagreeing about the same setting.
"""

import pytest

from security import MEMORY_STORAGE, resolve_storage_uri
from solverah.config import ConfigError, Settings

BASE_ENV = {
    "APP_ENV": "production",
    "DATABASE_URL": "postgresql://u:p@localhost:5432/solverah",
    "JWT_SECRET_KEY": "k" * 40,
    "JWT_COOKIE_SECURE": "true",
}


def test_defaults_to_memory_when_nothing_is_set():
    assert resolve_storage_uri({}) == MEMORY_STORAGE


def test_redis_url_is_used_as_the_backend():
    assert resolve_storage_uri({"REDIS_URL": "redis://cache:6379/0"}) == "redis://cache:6379/0"


def test_explicit_storage_uri_wins_over_redis_url():
    """An explicit override must beat the general-purpose Redis URL."""
    env = {"REDIS_URL": "redis://cache:6379/0", "RATELIMIT_STORAGE_URI": "redis://limits:6379/3"}

    assert resolve_storage_uri(env) == "redis://limits:6379/3"


def test_blank_values_are_ignored():
    """An unset-but-present variable (`REDIS_URL=`) must not become the URI."""
    assert resolve_storage_uri({"REDIS_URL": "   ", "RATELIMIT_STORAGE_URI": ""}) == MEMORY_STORAGE


@pytest.mark.parametrize(
    "env_extra",
    [
        {"REDIS_URL": "redis://cache:6379/0"},
        {"RATELIMIT_STORAGE_URI": "redis://limits:6379/3"},
        {"REDIS_URL": "redis://cache:6379/0", "RATELIMIT_STORAGE_URI": "redis://limits:6379/3"},
    ],
)
def test_config_and_limiter_agree_on_the_backend(env_extra):
    """The two layers must never disagree about the same setting."""
    env = dict(BASE_ENV, **env_extra)

    assert Settings.from_env(env).ratelimit_storage_uri == resolve_storage_uri(env)


def test_the_two_layers_agree_that_no_backend_is_memory():
    """The unset case, which `Settings` will no longer build in production.

    It still has to *resolve* the same way in both layers -- the disagreement
    this file exists for was one layer reporting "redis" while the other served
    memory. So the agreement is asserted against `resolve_storage_uri` directly
    and the production verdict on it is `test_memory_backend_in_production_is_fatal`.
    """
    env = dict(BASE_ENV, APP_ENV="development")

    assert Settings.from_env(env).ratelimit_storage_uri == resolve_storage_uri(env)
    assert resolve_storage_uri(env) == MEMORY_STORAGE


def test_memory_backend_in_production_is_fatal():
    """S1: what used to be a warning in both layers is now a refusal to boot.

    Fails against a build that only warns.
    """
    with pytest.raises(ConfigError) as exc:
        Settings.from_env(BASE_ENV)

    assert any("memory://" in p for p in exc.value.problems)


def test_redis_backend_in_production_does_not_warn():
    settings = Settings.from_env(dict(BASE_ENV, REDIS_URL="redis://cache:6379/0"))

    assert settings.warnings == []
