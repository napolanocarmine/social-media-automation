from social_automation.meta.graph_hints import meta_graph_error_action_hint


def test_hint_for_graph_200_permissions() -> None:
    msg = (
        "Meta Graph API (403) [200/]: (#200) The permission(s) "
        "pages_read_engagement,pages_manage_posts are not available. "
        "It could because either they are deprecated or need to be approved by App Review."
    )
    h = meta_graph_error_action_hint(msg)
    assert "Graph 200" in h
    assert "META_OAUTH_SCOPES" in h
    assert "meta-oauth-page-token --oauth-rerequest" in h
    assert "meta-debug-token" in h
    assert "meta-clear-page-token" in h


def test_hint_for_graph_200_generic_permissions_error() -> None:
    msg = "Meta Graph API (403) [200/]: (#200) Permissions error"
    h = meta_graph_error_action_hint(msg)
    assert "Graph 200" in h
    assert "meta-debug-token" in h
    assert "meta-clear-page-token" in h
    assert "oauth-rerequest" in h


def test_hint_empty_for_unrelated_message() -> None:
    assert meta_graph_error_action_hint("Something went wrong") == ""


def test_hint_for_instagram_whitelist_error_3() -> None:
    msg = "(#3) User must be on whitelist"
    h = meta_graph_error_action_hint(msg)
    assert "Instagram Graph" in h
    assert "whitelist" in h.lower()
