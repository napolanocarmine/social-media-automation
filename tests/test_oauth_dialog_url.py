from social_automation.meta.oauth_page_token import facebook_dialog_oauth_url


def test_facebook_dialog_oauth_url_includes_auth_type_rerequest() -> None:
    u = facebook_dialog_oauth_url(
        app_id="1",
        redirect_uri="https://example.com/cb",
        state="abc",
        graph_version="v22.0",
        scopes="pages_show_list,pages_manage_posts",
        auth_type="rerequest",
    )
    assert "auth_type=rerequest" in u
    assert "scope=pages_show_list" in u or "pages_manage_posts" in u


def test_facebook_dialog_oauth_url_omits_auth_type_when_empty() -> None:
    u = facebook_dialog_oauth_url(
        app_id="1",
        redirect_uri="https://example.com/cb",
        state="x",
        graph_version="v22.0",
        scopes="pages_show_list",
        auth_type="",
    )
    assert "auth_type" not in u
