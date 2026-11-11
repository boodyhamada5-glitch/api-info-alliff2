import httpx
import asyncio
import json
import time
import binascii
from typing import Tuple
from google.protobuf import json_format, message
from google.protobuf.message import Message
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from cachetools import TTLCache
import urllib3
from google_play_scraper import app as play_scraper

import AccountPersonalShow_pb2
import main_pb2

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

MAIN_KEY = b'Yg&tc%DEuh6%Zc^8'
MAIN_IV = b'6oyZDr22E3ychjM%'

USERAGENT = "Free%20Fire/2019118692 CFNetwork/3826.500.111.2.2 Darwin/24.4.0"
SUPPORTED_REGIONS = ["ME"]

JWT_API_URL = "https://ff-jwt-gen-api.lovable.app/api/public/token"

jwt_cache = TTLCache(maxsize=10, ttl=4 * 60 * 60)

current_server_domain = "ppmainecoonghj.com"
current_release_version = "OB55"
current_play_version = None
current_payload_template = None

DEFAULT_UID = "4744890160"
DEFAULT_PASSWORD = "AllFF_VIPO21LADJIP"


async def aes_encrypt(payload, key, iv):
    cipher = AES.new(key, AES.MODE_CBC, iv)
    return cipher.encrypt(pad(payload, AES.block_size))


async def get_playstore_version():
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            None,
            lambda: play_scraper('com.dts.freefireth', lang='hi', country='id')
        )
        return result.get("version")
    except Exception:
        return "1.132.8"


async def fetch_version_config():
    global current_play_version, current_release_version, current_server_domain
    app_version = await get_playstore_version()
    current_play_version = app_version
    api_url = (
        "https://version.ggwhitehawk.com/live/ver.php"
        f"?version={app_version}"
        "&lang=hi&device=android&channel=android"
        "&appstore=googleplay&region=BD"
        "&whitelist_version=1.3.0&whitelist_sp_version=1.0.0"
    )
    try:
        async with httpx.AsyncClient(verify=False, timeout=15.0) as c:
            response = await c.get(api_url)
            response.raise_for_status()
            data = response.json()
            if data.get("latest_release_version"):
                current_release_version = data["latest_release_version"]
            server_url = data.get("server_url") or ""
            if server_url:
                host = server_url.split("//")[-1].split("/")[0]
                if host.startswith("loginbp."):
                    current_server_domain = host[len("loginbp."):]
                elif host.startswith("clientbp."):
                    current_server_domain = host[len("clientbp."):]
    except Exception as e:
        print(f"[VERCONFIG] Error fetching version config: {e}")


async def create_jwt(region: str = "ME",
                     uid: str = DEFAULT_UID,
                     password: str = DEFAULT_PASSWORD) -> Tuple[str, str, str]:
    global current_server_domain
    try:
        cache_key = f"jwt_{uid}"
        if cache_key in jwt_cache:
            cached = jwt_cache[cache_key]
            return cached[0], cached[1], cached[2]

        print(f"Fetching JWT from API for UID: {uid}")

        async with httpx.AsyncClient(verify=False, timeout=30.0) as c:
            response = await c.get(
                JWT_API_URL,
                params={"uid": uid, "password": password}
            )

        if response.status_code != 200:
            raise Exception(f"JWT API returned status {response.status_code}")

        data = response.json()

        if not data.get("success"):
            raise Exception(f"JWT API failed: {data}")

        token = data.get("token")
        region_server = data.get("region") or region
        account_id = data.get("account_id")

        if not token:
            raise Exception("JWT API did not return a token")

        client_url = f"https://clientbp.{current_server_domain}"

        result = (f"Bearer {token}", region_server, client_url)
        jwt_cache[cache_key] = result

        print(f"JWT acquired for account_id={account_id}, region={region_server}")
        return result

    except Exception as e:
        print(f"Error in create_jwt: {str(e)}")
        cache_key = f"jwt_{uid}"
        if cache_key in jwt_cache:
            del jwt_cache[cache_key]
        raise e


async def json_to_proto(json_data: str, proto_message: Message) -> bytes:
    json_format.ParseDict(json.loads(json_data), proto_message)
    return proto_message.SerializeToString()


def decode_hex_protobuf(hex_data):
    try:
        byte_data = binascii.unhexlify(hex_data.replace(' ', ''))
        users = AccountPersonalShow_pb2.AccountPersonalShowInfo()
        users.ParseFromString(byte_data)
        return users
    except Exception as e:
        print(f"Protobuf decode error: {e}")
        raise e


async def GetAccountInformation(ID, UNKNOWN_ID, regionMain="ME",
                                endpoint="/api/clientbp/GetPlayerPersonalShow"):
    try:
        print(f"Fetching account info: ID={ID}, Region={regionMain}")

        if not isinstance(ID, str):
            ID = str(ID)
        if not isinstance(UNKNOWN_ID, str):
            UNKNOWN_ID = str(UNKNOWN_ID)

        json_data = json.dumps({
            "a": ID,
            "b": UNKNOWN_ID
        })

        encoded_result = await json_to_proto(json_data, main_pb2.GetPlayerPersonalShow())
        payload = await aes_encrypt(encoded_result, MAIN_KEY, MAIN_IV)

        regionMain = regionMain.upper()
        if regionMain not in SUPPORTED_REGIONS:
            return {
                "error": "Invalid request",
                "message": f"Unsupported 'region' parameter. Supported regions are: {', '.join(SUPPORTED_REGIONS)}."
            }

        token, region, serverUrl = await create_jwt(regionMain)

        req_headers = {
            "Host": f"clientbp.{current_server_domain}",
            "X-Unity-Version": "2018.4.11f1",
            "Accept": "*/*",
            "Authorization": token,
            "ReleaseVersion": current_release_version,
            "X-GA": "v1 1",
            'X-GA-SV': str(int(time.time())),
            "Accept-Encoding": "gzip, deflate, br",
            "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8",
            "Content-Type": "application/octet-stream",
            "User-Agent": USERAGENT,
            "Connection": "keep-alive"
        }

        full_url = serverUrl.rstrip('/') + endpoint

        async with httpx.AsyncClient(verify=False, timeout=30.0) as c:
            response = await c.post(full_url, data=payload, headers=req_headers)

        if response.status_code != 200:
            raise Exception(f"Server returned status {response.status_code}")

        hex_response = response.content.hex()
        message_obj = decode_hex_protobuf(hex_response)
        message_json = json_format.MessageToJson(message_obj)
        message_data = json.loads(message_json)

        message_data["release_version"] = current_release_version
        message_data["server_domain"] = current_server_domain
        message_data["play_version"] = current_play_version

        return message_data

    except Exception as e:
        print(f"Error in GetAccountInformation: {str(e)}")
        raise e


def fetch_latest_data():
    global current_play_version, current_release_version, current_server_domain
    try:
        result = play_scraper('com.dts.freefireth', lang='hi', country='id')
        current_play_version = result.get('version', '1.132.8')
    except Exception as e:
        print(f"[FETCH] Play store version fetch failed: {e}")

    try:
        ver_url = (
            "https://version.ggwhitehawk.com/live/ver.php"
            f"?version={current_play_version or '1.132.8'}"
            "&lang=hi&device=android&channel=android"
            "&appstore=googleplay&region=BD"
            "&whitelist_version=1.3.0&whitelist_sp_version=1.0.0"
        )
        r = httpx.get(ver_url, verify=False, timeout=15.0)
        r.raise_for_status()
        data = r.json()
        if data.get("latest_release_version"):
            current_release_version = data["latest_release_version"]
        server_url = data.get("server_url") or ""
        if server_url:
            host = server_url.split("//")[-1].split("/")[0]
            if host.startswith("loginbp."):
                current_server_domain = host[len("loginbp."):]
            elif host.startswith("clientbp."):
                current_server_domain = host[len("clientbp."):]
    except Exception as e:
        print(f"[FETCH] Version config fetch failed: {e}")

    print(f"Data loaded: Domain={current_server_domain}, Release={current_release_version}, Version={current_play_version}")
    return True


async def test():
    print("Testing JWT via external API...")
    try:
        token, region, server = await create_jwt("ME")
        print(f"Token: {token[:50]}...")
        print(f"Region: {region}")
        print(f"Server: {server}")
        print(f"Release Version: {current_release_version}")
        print(f"Server Domain: {current_server_domain}")
        print(f"Play Version: {current_play_version}")
    except Exception as e:
        print(f"Test failed: {e}")


if __name__ == "__main__":
    fetch_latest_data()
    asyncio.run(test())