from app.adapters.registry import registry


def test_registry_contains_launch_couriers():
    assert "tcs" in registry.adapters
    assert "pakpost" in registry.adapters
    assert "leopards" in registry.adapters
    assert "trax" in registry.adapters


def test_registry_descriptors_have_strategy_priority():
    descriptors = registry.list_descriptors()
    assert descriptors
    assert all(item.strategyPriority for item in descriptors)
