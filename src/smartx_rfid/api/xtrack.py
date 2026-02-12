import httpx
import logging
import xml.etree.ElementTree as ET

demo_server_url = "https://demo.smtx.com.br:6100/req"


class ApiXtrack:
    def __init__(self, base_url: str, timeout: int = 120):
        logging.info(f"[ XTRACK ] Initializing ApiXtrack with base_url: {base_url} and timeout: {timeout}")
        self.base_url = base_url
        self.timeout = timeout

    async def get(self, endpoint: str | None = None, params: dict = None, headers: dict = None, url: str | None = None):
        url = url or (f"{self.base_url}/{endpoint}" if endpoint else self.base_url)
        logging.info(f"[ XTRACK ] GET request to {url} with params: {params} and headers: {headers}")
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(url, params=params, headers=headers)
                response.raise_for_status()
                logging.info(f"[ XTRACK ] GET request successful: {response.status_code}")
                try:
                    return True, response.json()
                except Exception:
                    return True, {"raw_response": response.text}
            except httpx.HTTPStatusError as e:
                logging.error(f"[ XTRACK ] GET request failed: {e.response.status_code}")
                return False, {"error": f"HTTP error: {e.response.status_code}", "detail": str(e)}
            except Exception as e:
                logging.error(f"[ XTRACK ] GET request exception: {e}")
                return False, {"error": "Request failed", "detail": str(e)}

    async def post(
        self,
        endpoint: str | None = None,
        data: dict = None,
        json: dict = None,
        headers: dict = None,
        url: str | None = None,
    ):
        url = url or (f"{self.base_url}/{endpoint}" if endpoint else self.base_url)
        logging.info(f"[ XTRACK ] POST request to {url} with data: {data}, json: {json} and headers: {headers}")
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(url, data=data, json=json, headers=headers)
                response.raise_for_status()
                logging.info(f"[ XTRACK ] POST request successful: {response.status_code}")
                try:
                    return True, response.json()
                except Exception:
                    return True, {"raw_response": response.text}
            except httpx.HTTPStatusError as e:
                logging.error(f"[ XTRACK ] POST request failed: {e.response.status_code}")
                return False, {"error": f"HTTP error: {e.response.status_code}", "detail": str(e)}
            except Exception as e:
                logging.error(f"[ XTRACK ] POST request exception: {e}")
                return False, {"error": "Request failed", "detail": str(e)}

    async def test_connection(self):
        logging.info(f"[ XTRACK ] Testing connection to {self.base_url}")
        success, response = await self.get(url=self.base_url.replace("/req", ""))
        if success:
            logging.info("[ XTRACK ] Connection test successful")
        else:
            logging.error(f"[ XTRACK ] Connection test failed: {response}")
        return success, response

    async def get_objects(self):
        xml_payload = """
        <msg>
            <command>GetObject</command>
            <terminal>ERP</terminal>
        </msg>
        """
        headers = {"Content-Type": "application/xml"}
        # Faz o POST sem endpoint, enviando o XML como payload
        success, response = await self.post(data=xml_payload, headers=headers)
        xml_response = response.get("raw_response", None) if success else None
        data_list = []
        wanted_fields = [
            "IDCODE",
            "ACTIVE",
            "DESCRIPTION",
            "LOCATION_ID",
            "LAST_SEEN",
            "HOME_LOCATION_ID",
            "LAST_MODIFIED",
            "LAST_LOCATION",
        ]
        if success and xml_response:
            try:
                root = ET.fromstring(xml_response)
                for data_elem in root.findall(".//data"):
                    data_dict = {child.tag: child.text for child in data_elem if child.tag in wanted_fields}
                    data_list.append(data_dict)
                logging.info(f"[ XTRACK ] get_objects parsed data: {len(data_list)} items")
            except Exception as e:
                logging.error(f"[ XTRACK ] XML parsing error: {e}")
                return False, {"error": "XML parsing failed", "detail": str(e)}
        else:
            logging.info(f"[ XTRACK ] get_objects response: {xml_response}")
        return success, data_list if success else response

    async def get_locations(self):
        xml_payload = """
        <msg>
            <command>GetLocation</command>
            <terminal>ERP</terminal>
        </msg>
        """
        headers = {"Content-Type": "application/xml"}
        success, response = await self.post(data=xml_payload, headers=headers)
        xml_response = response.get("raw_response", None) if success else None
        location_list = []
        wanted_fields = ["ID", "NAME"]
        if success and xml_response:
            try:
                root = ET.fromstring(xml_response)
                for data_elem in root.findall(".//data"):
                    data_dict = {child.tag: child.text for child in data_elem if child.tag in wanted_fields}
                    location_list.append(data_dict)
                logging.info(f"[ XTRACK ] get_locations parsed data: {len(location_list)} items")
            except Exception as e:
                logging.error(f"[ XTRACK ] XML parsing error: {e}")
                return False, {"error": "XML parsing failed", "detail": str(e)}
        else:
            logging.info(f"[ XTRACK ] get_locations response: {xml_response}")
        return success, location_list if success else response
