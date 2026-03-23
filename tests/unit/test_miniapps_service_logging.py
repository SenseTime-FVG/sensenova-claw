from sensenova_claw.capabilities.miniapps.service import _extract_acp_update_text, _format_acp_update_log_message


def test_extract_acp_update_text_prefers_title_for_tool_call() -> None:
    update = {
        "sessionUpdate": "tool_call",
        "title": "Edit app.js",
        "status": "in_progress",
    }

    assert _extract_acp_update_text(update) == "Edit app.js"


def test_format_acp_update_log_message_includes_status() -> None:
    update = {
        "sessionUpdate": "tool_call",
        "title": "Edit app.js",
        "status": "completed",
    }

    assert _format_acp_update_log_message(update) == "ACP tool_call [completed]: Edit app.js"
