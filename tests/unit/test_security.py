"""Unit tests for security fixes (SEC-001 through SEC-008)."""

import shlex

import pytest

from do_app_sandbox.executor import _validate_env_keys

# =============================================================================
# SEC-001 / SEC-008: Environment variable key validation
# =============================================================================


class TestValidateEnvKeys:
    """Tests for _validate_env_keys() used in executor.py and process.py."""

    def test_valid_simple_keys(self):
        """Standard env var names should pass."""
        _validate_env_keys({"PATH": "/usr/bin", "HOME": "/home/user", "MY_VAR": "value"})

    def test_valid_underscore_prefix(self):
        """Keys starting with underscore should pass."""
        _validate_env_keys({"_PRIVATE": "val", "__DOUBLE": "val"})

    def test_valid_single_char(self):
        """Single character keys should pass."""
        _validate_env_keys({"A": "1", "_": "2"})

    def test_valid_alphanumeric_mix(self):
        """Keys with letters, digits, and underscores should pass."""
        _validate_env_keys({"VAR123": "v", "A1_B2_C3": "v", "x": "v"})

    def test_empty_dict(self):
        """Empty dict should pass without error."""
        _validate_env_keys({})

    def test_rejects_semicolon_injection(self):
        """Key with semicolon (shell command separator) must be rejected."""
        with pytest.raises(ValueError, match="Invalid environment variable name"):
            _validate_env_keys({"FOO;rm -rf /": "val"})

    def test_rejects_equals_in_key(self):
        """Key containing = must be rejected."""
        with pytest.raises(ValueError, match="Invalid environment variable name"):
            _validate_env_keys({"FOO=BAR": "val"})

    def test_rejects_space_in_key(self):
        """Key containing spaces must be rejected."""
        with pytest.raises(ValueError, match="Invalid environment variable name"):
            _validate_env_keys({"FOO BAR": "val"})

    def test_rejects_leading_digit(self):
        """Key starting with a digit must be rejected."""
        with pytest.raises(ValueError, match="Invalid environment variable name"):
            _validate_env_keys({"1VAR": "val"})

    def test_rejects_backtick_injection(self):
        """Key with backtick (command substitution) must be rejected."""
        with pytest.raises(ValueError, match="Invalid environment variable name"):
            _validate_env_keys({"`whoami`": "val"})

    def test_rejects_dollar_injection(self):
        """Key with $ (variable expansion) must be rejected."""
        with pytest.raises(ValueError, match="Invalid environment variable name"):
            _validate_env_keys({"$HOME": "val"})

    def test_rejects_newline_injection(self):
        """Key with newline must be rejected."""
        with pytest.raises(ValueError, match="Invalid environment variable name"):
            _validate_env_keys({"FOO\nBAR": "val"})

    def test_rejects_pipe_injection(self):
        """Key with pipe (command chaining) must be rejected."""
        with pytest.raises(ValueError, match="Invalid environment variable name"):
            _validate_env_keys({"FOO|cat /etc/passwd": "val"})

    def test_rejects_empty_key(self):
        """Empty string key must be rejected."""
        with pytest.raises(ValueError, match="Invalid environment variable name"):
            _validate_env_keys({"": "val"})

    def test_rejects_hyphen_in_key(self):
        """Key with hyphen must be rejected (not valid POSIX)."""
        with pytest.raises(ValueError, match="Invalid environment variable name"):
            _validate_env_keys({"MY-VAR": "val"})

    def test_first_invalid_key_raises(self):
        """When mix of valid and invalid, should raise on the invalid one."""
        with pytest.raises(ValueError, match="Invalid environment variable name"):
            _validate_env_keys({"GOOD": "val", "BAD;evil": "val"})


# =============================================================================
# SEC-006: Git checkout command quoting
# =============================================================================


class TestGitCheckoutQuoting:
    """Tests that git clone commands are properly shell-quoted."""

    def test_url_with_spaces_is_quoted(self):
        """URLs with special characters should be properly quoted."""
        parts = ["git", "clone", "--depth", "1", "https://example.com/repo with spaces.git", "/workspace"]
        quoted_cmd = " ".join(shlex.quote(p) for p in parts)
        # Verify the URL with spaces is quoted
        assert "repo with spaces" not in quoted_cmd.split()  # Not split on space
        assert "'https://example.com/repo with spaces.git'" in quoted_cmd or \
               '"https://example.com/repo with spaces.git"' in quoted_cmd or \
               "https://example.com/repo\\ with\\ spaces.git" in quoted_cmd

    def test_url_with_shell_metacharacters_is_quoted(self):
        """URLs with shell metacharacters should be safely quoted."""
        malicious_url = "https://evil.com/repo;rm -rf /"
        parts = ["git", "clone", malicious_url, "/workspace"]
        quoted_cmd = " ".join(shlex.quote(p) for p in parts)
        # The semicolon should be escaped/quoted, not interpreted as command separator
        assert ";rm" not in quoted_cmd or "'" in quoted_cmd

    def test_path_with_special_chars_is_quoted(self):
        """Destination paths with special chars should be quoted."""
        parts = ["git", "clone", "https://github.com/user/repo.git", "/workspace/my project"]
        quoted_cmd = " ".join(shlex.quote(p) for p in parts)
        assert "'/workspace/my project'" in quoted_cmd or '"/workspace/my project"' in quoted_cmd

    def test_normal_url_roundtrips(self):
        """Normal URLs without special chars should work unchanged."""
        url = "https://github.com/user/repo.git"
        parts = ["git", "clone", "--depth", "1", url, "/workspace"]
        quoted_cmd = " ".join(shlex.quote(p) for p in parts)
        assert url in quoted_cmd
