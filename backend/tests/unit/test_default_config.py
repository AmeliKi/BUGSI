from app.services.default_config import _deep_merge, get_default_config, merge_defaults


class TestGetDefaultConfig:
    def test_has_all_sections(self):
        config = get_default_config()
        expected_sections = {"camera", "telemetry", "upload", "power", "storage", "webserver"}
        assert expected_sections == set(config.keys())

    def test_returns_deep_copy(self):
        config1 = get_default_config()
        config1["camera"]["resolution_width"] = 999
        config2 = get_default_config()
        assert config2["camera"]["resolution_width"] != 999

    def test_camera_section_has_fields(self):
        config = get_default_config()
        assert "resolution_width" in config["camera"]
        assert "resolution_height" in config["camera"]
        assert "jpeg_quality" in config["camera"]


class TestDeepMerge:
    def test_override_wins(self):
        base = {"a": 1, "b": 2}
        override = {"b": 3}
        result = _deep_merge(base, override)
        assert result == {"a": 1, "b": 3}

    def test_adds_new_keys(self):
        base = {"a": 1}
        override = {"b": 2}
        result = _deep_merge(base, override)
        assert result == {"a": 1, "b": 2}

    def test_nested_merge(self):
        base = {"section": {"a": 1, "b": 2}}
        override = {"section": {"b": 3, "c": 4}}
        result = _deep_merge(base, override)
        assert result == {"section": {"a": 1, "b": 3, "c": 4}}

    def test_does_not_mutate_base(self):
        base = {"a": {"x": 1}}
        override = {"a": {"x": 2}}
        _deep_merge(base, override)
        assert base["a"]["x"] == 1


class TestMergeDefaults:
    def test_empty_dict_returns_full_defaults(self):
        result = merge_defaults({})
        defaults = get_default_config()
        assert result == defaults

    def test_preserves_device_values(self):
        device = {"camera": {"resolution_width": 1920}}
        result = merge_defaults(device)
        assert result["camera"]["resolution_width"] == 1920

    def test_adds_missing_keys_within_section(self):
        device = {"camera": {"resolution_width": 1920}}
        result = merge_defaults(device)
        # Other camera fields should come from defaults
        assert "resolution_height" in result["camera"]
        assert "jpeg_quality" in result["camera"]

    def test_adds_missing_sections(self):
        device = {"camera": {"resolution_width": 1920}}
        result = merge_defaults(device)
        assert "telemetry" in result
        assert "upload" in result
        assert "power" in result
        assert "storage" in result
        assert "webserver" in result

    def test_full_config_unchanged(self):
        defaults = get_default_config()
        device = get_default_config()
        device["camera"]["resolution_width"] = 1920
        result = merge_defaults(device)
        assert result["camera"]["resolution_width"] == 1920
        # Other values should match defaults
        assert result["telemetry"] == defaults["telemetry"]
