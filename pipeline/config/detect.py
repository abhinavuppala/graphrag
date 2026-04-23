import re
from dataclasses import dataclass


@dataclass
class DomainConfig:
    name: str
    entity_types: list[str]
    description: str


DOMAINS: dict[str, DomainConfig] = {
    "pub-sub": DomainConfig(
        name="pub-sub",
        entity_types=[
            "service", "component", "module", "function", "error",
            "topic", "queue", "subscription", "message", "config",
        ],
        description="pub-sub / message broker system",
    ),
    "web-api": DomainConfig(
        name="web-api",
        entity_types=[
            "endpoint", "handler", "middleware", "model", "service",
            "controller", "router", "schema", "auth", "config",
        ],
        description="web API / REST service",
    ),
    "database": DomainConfig(
        name="database",
        entity_types=[
            "table", "model", "query", "index", "migration",
            "transaction", "schema", "connection", "cache", "config",
        ],
        description="database system",
    ),
}

_PUB_SUB = frozenset([
    "nats", "kafka", "rabbitmq", "pulsar", "jetstream", "activemq", "nsq",
    "pub-sub", "pubsub", "message queue", "message broker", "event stream",
    "consumer group", "producer", "subscriber", "publisher",
])

_WEB_API = frozenset([
    "rest api", "http server", "graphql", "grpc", "fastapi", "django",
    "flask", "express", "spring boot", "gin", "echo", "fiber", "actix",
])

_DATABASE = frozenset([
    "postgres", "mysql", "sqlite", "mongodb", "redis", "cassandra",
    "database engine", "storage engine", "orm", "query planner",
])


def _matches(text: str, keywords: frozenset) -> bool:
    """Whole-word keyword match — prevents 'gin' matching 'engine'."""
    return any(re.search(r"\b" + re.escape(kw) + r"\b", text) for kw in keywords)


def detect_domain(detected_framework: str, detected_language: str = "") -> DomainConfig:
    """Map Phase 1 detected framework/language to a domain config."""
    text = (detected_framework + " " + detected_language).lower()

    if _matches(text, _PUB_SUB):
        return DOMAINS["pub-sub"]
    if _matches(text, _WEB_API):
        return DOMAINS["web-api"]
    if _matches(text, _DATABASE):
        return DOMAINS["database"]

    # Default — all current clients are pub-sub
    return DOMAINS["pub-sub"]
