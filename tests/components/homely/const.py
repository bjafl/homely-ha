TEST_USERNAME = "test@example.com"
TEST_PASSWORD = "password123"
TEST_LOCATION_ID = "550e8400-e29b-41d4-a716-446655440100"
TEST_LOCATION_NAME = "Test Location"
TEST_USER_ID = "691385ad-defe-4eb1-b0cc-1da674ba597d"

FAKE_TOKEN_RESPONSE = {
    "access_token": "a7263e8d-9d2e-46f4-832f-07159acc8aa8",
    "expires_in": 1800,
    "refresh_token": "3a894f45-4d45-46cf-a424-fc57a1369fe5",
    "refresh_expires_in": 1800,
    "token_type": "bearer",
    "not-before-policy": 1618215605,
    "session_state": "ebc511e7-0a53-40c4-a6a6-95efd5c82f53",
    "scope": "",
}

FAKE_LOCATION = {
    "name": TEST_LOCATION_NAME,
    "locationId": TEST_LOCATION_ID,
    "role": "OWNER",
    "userId": TEST_USER_ID,
    "gatewayserial": "GW123456",
    "partnerCode": 1234,
}

FAKE_LOCATIONS_RESPONSE = [
    FAKE_LOCATION,
    {
        "name": "Another Location",
        "locationId": "d4fe152b-47ec-4011-b257-d5edf7668201",
        "role": "ADMIN",
        "userId": TEST_USER_ID,
        "gatewayserial": "GW654321",
        "partnerCode": 1234,
    },
]

FAKE_HOME = {
    "locationId": TEST_LOCATION_ID,
    "gatewayserial": "GW123456",
    "name": TEST_LOCATION_NAME,
    "alarmState": "DISARMED",
    "userRoleAtLocation": "OWNER",
    "devices": [],
}

FAKE_WS_EVENT = {
    "type": "device-state-changed",
    "data": {
        "locationId": "c36ba8f1-597a-4e64-bc4c-107ae3ebbe85",
        "rootLocationId": TEST_LOCATION_ID,
        "gatewayId": "20ca8a03-526f-4d34-8a03-a72228081f00",
        "deviceId": "d9016467-77b6-4b32-88ae-a6eb296cff9a",
        "modelId": "98257573-ae4d-4170-a8f2-83f337b4deb2",
        "change": {
            "feature": "diagnostic",
            "stateName": "networklinkstrength",
            "value": 84,
            "lastUpdated": "2025-10-05T07:01:39.181Z",
        },
        "changes": [
            {
                "feature": "diagnostic",
                "stateName": "networklinkstrength",
                "value": 84,
                "lastUpdated": "2025-10-05T07:01:39.181Z",
            }
        ],
        "partnerCode": 1234,
    },
}
