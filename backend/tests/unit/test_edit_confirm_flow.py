"""Unit tests verifying edit confirm parity, single projection passes, and projector error aborts."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from services.gemini.edit_voice import _dispatch_voice_tool, _apply_live_edits

def get_base_project() -> dict:
    return {
        "tracks": [
            {
                "id": "track-overlay",
                "name": "Overlays",
                "type": "element",
                "elements": []
            }
        ]
    }

@pytest.mark.asyncio
async def test_single_projection_pass():
    """Verify that a confirmed add_hook_title command does not get applied twice."""
    draft_commands = [{"kind": "add_hook_title", "args": {"text": "My Hook", "duration_seconds": 2.0}}]
    
    mock_decision_queue = asyncio.Queue()
    mock_decision_queue.put_nowait({"decision": "confirm"})
    
    mock_on_event = AsyncMock()
    mock_fdb = AsyncMock()
    mock_fdb.get_project.return_value = {"project_json": get_base_project()}
    
    with patch("services.storage.firestore_db.get_project", mock_fdb.get_project):
        with patch("services.storage.firestore_db.save_project", mock_fdb.save_project):
            result = await _dispatch_voice_tool(
                name="apply_live_edits",
                args={},
                project_id="test_proj",
                project_data={},
                draft_commands=draft_commands,
                current_project_json=get_base_project(),
                editor_context={"playhead_seconds": 0.0},
                on_event=mock_on_event,
                decision_queue=mock_decision_queue,
                get_live_state=lambda: {"project_json": get_base_project()}
            )

    assert result.get("error") is None
    
    # Verify save_project was called exactly once
    assert mock_fdb.save_project.call_count == 1
    
    # Check the actual saved JSON payload
    saved_updates = mock_fdb.save_project.call_args[0][1]
    saved_json = saved_updates["project_json"]
    
    # Count how many Hook titles were added
    overlay_track = next(t for t in saved_json["tracks"] if t["name"] == "Overlays")
    hook_elements = [e for e in overlay_track["elements"] if e.get("t") == "My Hook"]
    
    assert len(hook_elements) == 1, "add_hook_title was applied twice instead of once!"

@pytest.mark.asyncio
async def test_voice_confirm_aborts_on_projector_errors():
    """Verify that voice confirmation prevents saving if projector throws errors."""
    
    # A fake command that we know will fail
    draft_commands = [{"kind": "move_selected_element", "args": {"dy": -50.0}}]
    
    mock_decision_queue = asyncio.Queue()
    mock_decision_queue.put_nowait({"decision": "confirm"})
    
    mock_on_event = AsyncMock()
    mock_fdb = AsyncMock()
    mock_fdb.get_project.return_value = {"project_json": get_base_project()}
    
    with patch("services.storage.firestore_db.get_project", mock_fdb.get_project):
        with patch("services.storage.firestore_db.save_project", mock_fdb.save_project):
            result = await _dispatch_voice_tool(
                name="apply_live_edits",
                args={},
                project_id="test_proj",
                project_data={},
                draft_commands=draft_commands,
                current_project_json=get_base_project(),
                editor_context={"selected_element_ids": []}, # Empty selection -> projector error
                on_event=mock_on_event,
                decision_queue=mock_decision_queue,
                get_live_state=lambda: {"project_json": get_base_project()}
            )

    # The save operation should NOT have been called
    mock_fdb.save_project.assert_not_called()
    assert result.get("error") is not None
    assert "rejected" in result["error"]
