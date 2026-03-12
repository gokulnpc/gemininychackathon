from unittest.mock import patch, AsyncMock
import pytest

from services.storage.assets import resolve_asset_url, resolve_asset_metadata

@pytest.mark.asyncio
async def test_resolve_asset_url_success():
    mock_meta = {"uid": "user123", "gcs_key": "some/gcs/key.jpg"}
    with patch("services.storage.gcs.load_json", new_callable=AsyncMock, return_value=mock_meta):
        with patch("services.storage.gcs.generate_presigned_url", new_callable=AsyncMock, return_value="https://signed.url/image.jpg"):
            url = await resolve_asset_url("user123", "images", "asset123")
            assert url == "https://signed.url/image.jpg"

@pytest.mark.asyncio
async def test_resolve_asset_url_mismatched_uid():
    mock_meta = {"uid": "user_other", "gcs_key": "some/gcs/key.jpg"}
    with patch("services.storage.gcs.load_json", new_callable=AsyncMock, return_value=mock_meta):
        url = await resolve_asset_url("user123", "images", "asset123")
        assert url is None

@pytest.mark.asyncio
async def test_resolve_asset_url_missing_gcs_key():
    mock_meta = {"uid": "user123"}
    with patch("services.storage.gcs.load_json", new_callable=AsyncMock, return_value=mock_meta):
        url = await resolve_asset_url("user123", "images", "asset123")
        assert url is None


@pytest.mark.asyncio
async def test_list_user_assets_correct_shape():
    from services.storage.assets import list_user_assets
    
    mock_keys = [
        "user_assets/user1/images/asset1/meta.json",
        "user_assets/user1/images/asset2/meta.json",
        "user_assets/user1/images/asset3/thumb.jpg", # should be skipped
    ]
    
    mock_metas = [
        {"id": "asset1", "filename": "first.jpg", "uploaded_at": "2024-01-01T10:00:00Z"},
        {"id": "asset2", "filename": "second.jpg", "uploaded_at": "2024-01-02T10:00:00Z"},
    ]
    
    async def mock_load_json(key):
        if "asset1" in key: return mock_metas[0]
        if "asset2" in key: return mock_metas[1]
        return None
        
    with patch("services.storage.gcs.list_keys", new_callable=AsyncMock, return_value=mock_keys):
        with patch("services.storage.gcs.load_json", new=mock_load_json):
            assets = await list_user_assets("user1", "images", limit=10)
            
            assert len(assets) == 2
            # Should be sorted newest first
            assert assets[0]["id"] == "asset2"
            assert assets[1]["id"] == "asset1"
            # Ensure correct keys are present
            assert "filename" in assets[0]
            assert "uploaded_at" in assets[0]
