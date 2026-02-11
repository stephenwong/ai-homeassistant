#!/usr/bin/env python3
"""Home Assistant API Diagnostic Tool.

Comprehensive testing of various API endpoints and entity operations.
Combines functionality from multiple diagnostic scripts.
"""

import json
import os

import requests

from tools.common import load_env_file


def get_config():
    """Load configuration from environment."""
    load_env_file()
    return {
        "ha_url": os.getenv("HA_URL", "http://homeassistant.local:8123"),
        "token": os.getenv("HA_TOKEN", ""),
    }


def test_api_connection(ha_url, token):
    """Test basic API connection."""
    print("🔗 Testing API Connection...")
    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(f"{ha_url}/api/", headers=headers, timeout=10)

        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   Message: {data.get('message', 'No message')}")
            return True
        else:
            print(f"   Error: {response.text}")
            return False
    except Exception as e:
        print(f"   Exception: {e}")
        return False


def test_api_endpoints(ha_url, token):
    """Test various API endpoints to find entity registry access."""
    print("\n🔍 Testing Various API Endpoints...")

    headers = {"Authorization": f"Bearer {token}"}

    endpoints_to_test = [
        ("/api/config/entity_registry", "Entity Registry"),
        ("/api/config/entity_registry/list", "Entity Registry List"),
        ("/api/states", "Entity States"),
        ("/api/config", "Configuration"),
        ("/api/config/core", "Core Configuration"),
        ("/api/hassio/supervisor/api/config", "Supervisor Config"),
        ("/api/template", "Template API"),
    ]

    successful_endpoints = []

    for endpoint, description in endpoints_to_test:
        try:
            print(f"\n   Testing: {endpoint} ({description})")
            response = requests.get(f"{ha_url}{endpoint}", headers=headers, timeout=10)
            print(f"   Status: {response.status_code}")

            if response.status_code == 200:
                successful_endpoints.append(endpoint)
                try:
                    data = response.json()
                    if isinstance(data, list):
                        print(f"   ✅ List with {len(data)} items")
                        if len(data) > 0:
                            print(f"      Sample type: {type(data[0])}")
                    elif isinstance(data, dict):
                        keys = list(data.keys())[:5]
                        print(f"   ✅ Dict with keys: {keys}")
                    else:
                        print(f"   ✅ {type(data)}")
                except Exception:
                    print(f"   ✅ Non-JSON response ({len(response.text)} chars)")
            else:
                print(f"   ❌ {response.text[:100]}")

        except Exception as e:
            print(f"   ❌ Exception: {e}")

    return successful_endpoints


def test_entity_registry_read(ha_url, token):
    """Test reading entity registry."""
    print("\n📋 Testing Entity Registry Read Access...")
    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(
            f"{ha_url}/api/config/entity_registry", headers=headers, timeout=10
        )

        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ Found {len(data)} entities")

            # Sample first 3 entities for inspection
            sample_entities = data[:3]
            for entity in sample_entities:
                entity_id = entity.get("entity_id")
                print(f"   ✅ Sample: {entity_id}")
                print(f"      Platform: {entity.get('platform')}")
                print(f"      Device ID: {entity.get('device_id')}")
                print(f"      Unique ID: {entity.get('unique_id')}")

            return sample_entities
        else:
            print(f"   ❌ Error: {response.text}")
            return []
    except Exception as e:
        print(f"   ❌ Exception: {e}")
        return []


def test_states_endpoint(ha_url, token):
    """Test the /api/states endpoint to see entity data."""
    print("\n📊 Testing States Endpoint for Entity Info...")
    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(f"{ha_url}/api/states", headers=headers, timeout=10)

        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            states = response.json()
            print(f"   ✅ Found {len(states)} states")

            # Sample first 3 entities for inspection
            for state in states[:3]:
                entity_id = state.get("entity_id")
                print(f"   ✅ Sample: {entity_id}")
                attrs = list(state.get("attributes", {}).keys())[:5]
                print(f"      Attributes: {attrs}")

            return len(states) > 0
        else:
            print(f"   ❌ Error: {response.text}")
            return False
    except Exception as e:
        print(f"   ❌ Exception: {e}")
        return False


def test_entity_rename(ha_url, token, entity_data_list):
    """Test renaming a single entity using multiple methods."""
    print("\n🔄 Testing Entity Rename Methods...")

    if not entity_data_list:
        print("   ❌ No entity data to test with")
        return False

    entity_data = entity_data_list[0]  # Use first discovered entity
    old_id = entity_data.get("entity_id", "unknown")
    domain = old_id.split(".")[0] if "." in old_id else "entity"
    new_id = f"{domain}.rename_test_temp"

    print(f"   Testing rename: {old_id} → {new_id}")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    # Method 1: Direct entity registry update
    try:
        print("\n   Method 1: Direct registry update...")
        data = {"new_entity_id": new_id}
        response = requests.post(
            f"{ha_url}/api/config/entity_registry/{old_id}",
            headers=headers,
            json=data,
            timeout=10,
        )

        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            print("   ✅ Method 1 successful!")
            return True
        else:
            print(f"   ❌ Method 1 failed: {response.text}")

    except Exception as e:
        print(f"   ❌ Method 1 exception: {e}")

    # Method 2: Update endpoint
    try:
        print("\n   Method 2: Update endpoint...")
        response = requests.post(
            f"{ha_url}/api/config/entity_registry/update",
            headers=headers,
            json={"entity_id": old_id, "new_entity_id": new_id},
            timeout=10,
        )

        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            print("   ✅ Method 2 successful!")
            return True
        else:
            print(f"   ❌ Method 2 failed: {response.text}")

    except Exception as e:
        print(f"   ❌ Method 2 exception: {e}")

    return False


def test_service_call_method(ha_url, token, entity_data_list):
    """Test if we can rename via service calls."""
    print("\n🔧 Testing Service Call Method...")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    # Use first discovered entity, or skip if none available
    if not entity_data_list:
        print("   ❌ No entity data to test with")
        return

    target_entity = entity_data_list[0].get("entity_id", "unknown")

    # Test calling homeassistant.update_entity service
    try:
        service_data = {
            "entity_id": target_entity,
            # This changes friendly name, not entity_id
            "name": "Rename Test Temp",
        }

        response = requests.post(
            f"{ha_url}/api/services/homeassistant/update_entity",
            headers=headers,
            json=service_data,
            timeout=10,
        )

        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            print("   ✅ Service call successful (friendly name only)")
            print("   Note: This only changes display name, not entity_id")
        else:
            print(f"   ❌ Service call failed: {response.text}")

    except Exception as e:
        print(f"   ❌ Exception: {e}")


def show_websocket_info():
    """Show information about WebSocket method."""
    print("\n🌐 WebSocket API Information...")
    print("   Entity registry operations likely require WebSocket API:")
    print("   • WebSocket URL: ws://homeassistant.local:8123/api/websocket")
    print("   • Auth: Send auth message with Bearer token")
    print("   • List entities: {'type': 'config/entity_registry/list'}")
    print(
        "   • Update entity: {'type': 'config/entity_registry/update', "
        "'entity_id': '...', 'new_entity_id': '...'}"
    )

    websocket_example = {
        "id": 1,
        "type": "config/entity_registry/update",
        "entity_id": "<old_entity_id>",
        "new_entity_id": "<new_entity_id>",
    }

    print("\n   Example WebSocket command:")
    print(f"   {json.dumps(websocket_example, indent=2)}")


def main():
    """Run main diagnostic function."""
    print("🏠 Home Assistant API Diagnostic Tool")
    print("=" * 60)

    config = get_config()
    ha_url = config["ha_url"]
    token = config["token"]

    if not token:
        print("❌ No HA_TOKEN found in .env file!")
        print("   Create a .env file with: HA_TOKEN=your_long_lived_access_token")
        return

    print(f"🔗 Testing connection to: {ha_url}")

    # Test 1: Basic connection
    if not test_api_connection(ha_url, token):
        print("❌ Basic connection failed - stopping tests")
        return

    # Test 2: Explore available endpoints
    successful_endpoints = test_api_endpoints(ha_url, token)

    # Test 3: Entity registry read
    entity_data = test_entity_registry_read(ha_url, token)

    # Test 4: States endpoint
    states_work = test_states_endpoint(ha_url, token)

    # Test 5: Entity rename attempts
    test_entity_rename(ha_url, token, entity_data)

    # Test 6: Service call method
    test_service_call_method(ha_url, token, entity_data)

    # Test 7: WebSocket method info
    show_websocket_info()

    # Summary
    print("\n" + "=" * 60)
    print("🎯 DIAGNOSTIC SUMMARY")
    print("=" * 60)
    print(f"✅ Working endpoints: {len(successful_endpoints)}")
    registry_access = "Yes" if entity_data else "No (likely WebSocket only)"
    print(f"✅ Entity registry access: {registry_access}")
    states_status = "Yes" if states_work else "No"
    print(f"✅ States endpoint: {states_status}")
    print("✅ Entity renaming: Requires WebSocket API or UI")
    print("\n📝 RECOMMENDATIONS:")
    print("   1. Use WebSocket API for entity registry operations")
    print("   2. REST API works for states but not entity management")
    print("   3. Service calls only change friendly names, not entity IDs")
    print("   4. Manual UI renaming may be most reliable option")


if __name__ == "__main__":
    main()
