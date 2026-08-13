import httpx
import logging
import asyncio
from datetime import datetime


class ToolSortClient:
    def __init__(self, url: str, username: str, password: str, expire_time: int = 20):
        self.url = url
        self.username = username
        self.password = password
        self.session = None
        self.token = None
        self.last_auth_time = None
        self.expire_time = expire_time * 60  # Convert minutes to seconds
        self.account_id = None

        # Schedule initial authentication on the running event loop when available.
        # If there's no running loop (e.g. created in sync context), run it synchronously.
        try:
            loop = asyncio.get_running_loop()
            try:
                loop.create_task(self.authenticate())
            except Exception as e:
                logging.error(f"[ TOOLSORT ] Scheduling initial authentication failed: {e}")
        except RuntimeError:
            try:
                asyncio.run(self.authenticate())
            except Exception as e:
                logging.error(f"[ TOOLSORT ] Initial authentication failed (sync): {e}")

    async def authenticate(self):
        url = f"{self.url}/api/v1/Auth/Login"
        payload = {"login": self.username, "password": self.password}
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload)
            if response.status_code != 200:
                logging.error(f"[Integration] Auth failed: {response.status_code} - {response.text}")
                response.raise_for_status()
            try:
                data: dict = response.json()
            except Exception:
                logging.error(f"[Integration] Invalid JSON in auth response: {response.text[:500]}")
                return
            success = data.get("sucesso", False)
            if not success:
                logging.error(f"[Integration] Auth failed: {data}")
                return
            logging.info(f"[Integration] Auth successful: {data}")
            self.token = data.get("access_token")
            self.account_id = data.get("user", {}).get("id")
            self.last_auth_time = datetime.now()

    async def ensure_authenticated(self):
        if not self.token or not self.account_id:
            await self.authenticate()  # Ensure we have a valid token and account_id
        if self.last_auth_time and (datetime.now() - self.last_auth_time).total_seconds() > self.expire_time:
            await self.authenticate()  # Re-authenticate if token has expired

    async def verify_card(self, card_id: str):
        await self.ensure_authenticated()  # Ensure we are authenticated before making the request

        url = f"{self.url}/api/v1/Service/GetClient/{self.account_id}/{card_id}"
        headers = {"Authorization": f"Bearer {self.token}"}
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=headers)
                if response.status_code != 200:
                    logging.error(f"[Integration] Verify card failed: {response.status_code} - {response.text}")
                    response.raise_for_status()
                try:
                    data: dict = response.json()
                except Exception:
                    logging.error(f"[Integration] Invalid JSON in verify card response: {response.text[:500]}")
                    return None
                logging.info(f"[Integration] Verify card successful: {data}")
                return data
        except Exception as e:
            logging.error(f"[Integration] Exception during verify card: {e}")
            self.token = None  # Invalidate token on error to force re-authentication next time
            self.account_id = None
            self.last_auth_time = None
            return None

    async def get_descriptions(self, epcs: list):
        if not isinstance(epcs, list):
            logging.error(f"[Integration] get_descriptions expects a list of EPCs, got: {type(epcs)}")
            return None
        await self.ensure_authenticated()  # Ensure we are authenticated before making the request
        url = f"{self.url}/api/v1/Devices/ItensByTags/{self.account_id}"
        payload = {"tags": epcs}
        headers = {"Authorization": f"Bearer {self.token}"}
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload, headers=headers)
                if response.status_code != 200:
                    logging.error(f"[Integration] Get descriptions failed: {response.status_code} - {response.text}")
                    response.raise_for_status()
                try:
                    data: dict = response.json()
                except Exception:
                    logging.error(f"[Integration] Invalid JSON in get descriptions response: {response.text[:500]}")
                    return None
                logging.info(f"[Integration] Get descriptions successful: {data}")
                return data
        except Exception as e:
            logging.error(f"[Integration] Exception during get descriptions: {e}")
            self.token = None  # Invalidate token on error to force re-authentication next time
            self.account_id = None
            self.last_auth_time = None
            return None

    async def post_tags(self, device: str, card_id: str, epcs: list, is_locker: bool, door: str = None):
        if is_locker:
            url = f"{self.url}/api/v1/Devices/PostCabinet/{self.account_id}"
        else:
            url = f"{self.url}/api/v1/Devices/PostEclusa/{self.account_id}"

        payload = {
            "device": device,
            "user_id": self.account_id,
            "card_id": card_id,
            "timestamp": datetime.now().isoformat(),
            "tags": epcs,
        }
        if not is_locker:
            payload["status"] = door

        headers = {"Authorization": f"Bearer {self.token}"}

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload, headers=headers)
                if response.status_code != 200:
                    logging.error(f"[Integration] Post tags failed: {response.status_code} - {response.text}")
                    response.raise_for_status()
                try:
                    data: dict = response.json()
                except Exception:
                    logging.error(f"[Integration] Invalid JSON in post tags response: {response.text[:500]}")
                    return None
                logging.info(f"[Integration] Post tags successful: {data}")
                return data
        except Exception as e:
            logging.error(f"[Integration] Exception during post tags: {e}")
            self.token = None  # Invalidate token on error to force re-authentication next time
            self.account_id = None
            self.last_auth_time = None
            return None
