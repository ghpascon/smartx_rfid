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

    # GET INFORMATION METHODS
    async def get_categories(self):
        xml_payload = """
        <msg>
            <command>GetCategory</command>
            <terminal>ERP</terminal>
        </msg>
        """
        headers = {"Content-Type": "application/xml"}
        success, response = await self.post(data=xml_payload, headers=headers)
        xml_response = response.get("raw_response", None) if success else None
        category_list = []
        if success and xml_response:
            try:
                root = ET.fromstring(xml_response)
                for data_elem in root.findall(".//data"):
                    data_dict = {child.tag: child.text for child in data_elem}
                    category_list.append(data_dict)
                logging.info(f"[ XTRACK ] get_categories parsed data: {len(category_list)} items")
            except Exception as e:
                logging.error(f"[ XTRACK ] XML parsing error: {e}")
                return False, {"error": "XML parsing failed", "detail": str(e)}
        else:
            logging.info(f"[ XTRACK ] get_categories response: {xml_response}")
        return success, category_list if success else response

    async def get_conditions(self):
        xml_payload = """
        <msg>
            <command>GetCondition</command>
            <terminal>ERP</terminal>
        </msg>
        """
        headers = {"Content-Type": "application/xml"}
        success, response = await self.post(data=xml_payload, headers=headers)
        xml_response = response.get("raw_response", None) if success else None
        condition_list = []
        if success and xml_response:
            try:
                root = ET.fromstring(xml_response)
                for data_elem in root.findall(".//data"):
                    data_dict = {child.tag: child.text for child in data_elem}
                    condition_list.append(data_dict)
                logging.info(f"[ XTRACK ] get_conditions parsed data: {len(condition_list)} items")
            except Exception as e:
                logging.error(f"[ XTRACK ] XML parsing error: {e}")
                return False, {"error": "XML parsing failed", "detail": str(e)}
        else:
            logging.info(f"[ XTRACK ] get_conditions response: {xml_response}")
        return success, condition_list if success else response

    async def get_cost_centers(self):
        xml_payload = """
        <msg>
            <command>GetCostCenter</command>
            <terminal>ERP</terminal>
        </msg>
        """
        headers = {"Content-Type": "application/xml"}
        success, response = await self.post(data=xml_payload, headers=headers)
        xml_response = response.get("raw_response", None) if success else None
        cost_center_list = []
        if success and xml_response:
            try:
                root = ET.fromstring(xml_response)
                for data_elem in root.findall(".//data"):
                    data_dict = {child.tag: child.text for child in data_elem}
                    cost_center_list.append(data_dict)
                logging.info(f"[ XTRACK ] get_cost_centers parsed data: {len(cost_center_list)} items")
            except Exception as e:
                logging.error(f"[ XTRACK ] XML parsing error: {e}")
                return False, {"error": "XML parsing failed", "detail": str(e)}
        else:
            logging.info(f"[ XTRACK ] get_cost_centers response: {xml_response}")
        return success, cost_center_list if success else response

    async def get_custodians(self):
        xml_payload = """
        <msg>
            <command>GetCustodian</command>
            <terminal>ERP</terminal>
        </msg>
        """
        headers = {"Content-Type": "application/xml"}
        success, response = await self.post(data=xml_payload, headers=headers)
        xml_response = response.get("raw_response", None) if success else None
        custodian_list = []
        if success and xml_response:
            try:
                root = ET.fromstring(xml_response)
                for data_elem in root.findall(".//data"):
                    data_dict = {child.tag: child.text for child in data_elem}
                    custodian_list.append(data_dict)
                logging.info(f"[ XTRACK ] get_custodians parsed data: {len(custodian_list)} items")
            except Exception as e:
                logging.error(f"[ XTRACK ] XML parsing error: {e}")
                return False, {"error": "XML parsing failed", "detail": str(e)}
        else:
            logging.info(f"[ XTRACK ] get_custodians response: {xml_response}")
        return success, custodian_list if success else response

    async def get_departments(self):
        xml_payload = """
        <msg>
            <command>GetDepartment</command>
            <terminal>ERP</terminal>
        </msg>
        """
        headers = {"Content-Type": "application/xml"}
        success, response = await self.post(data=xml_payload, headers=headers)
        xml_response = response.get("raw_response", None) if success else None
        department_list = []
        if success and xml_response:
            try:
                root = ET.fromstring(xml_response)
                for data_elem in root.findall(".//data"):
                    data_dict = {child.tag: child.text for child in data_elem}
                    department_list.append(data_dict)
                logging.info(f"[ XTRACK ] get_departments parsed data: {len(department_list)} items")
            except Exception as e:
                logging.error(f"[ XTRACK ] XML parsing error: {e}")
                return False, {"error": "XML parsing failed", "detail": str(e)}
        else:
            logging.info(f"[ XTRACK ] get_departments response: {xml_response}")
        return success, department_list if success else response

    async def get_disposals(self):
        xml_payload = """
        <msg>
            <command>GetDisposal</command>
            <terminal>ERP</terminal>
        </msg>
        """
        headers = {"Content-Type": "application/xml"}
        success, response = await self.post(data=xml_payload, headers=headers)
        xml_response = response.get("raw_response", None) if success else None
        disposal_list = []
        if success and xml_response:
            try:
                root = ET.fromstring(xml_response)
                for data_elem in root.findall(".//data"):
                    data_dict = {child.tag: child.text for child in data_elem}
                    disposal_list.append(data_dict)
                logging.info(f"[ XTRACK ] get_disposals parsed data: {len(disposal_list)} items")
            except Exception as e:
                logging.error(f"[ XTRACK ] XML parsing error: {e}")
                return False, {"error": "XML parsing failed", "detail": str(e)}
        else:
            logging.info(f"[ XTRACK ] get_disposals response: {xml_response}")
        return success, disposal_list if success else response

    async def get_dispositions(self):
        xml_payload = """
        <msg>
            <command>GetDisposition</command>
            <terminal>ERP</terminal>
        </msg>
        """
        headers = {"Content-Type": "application/xml"}
        success, response = await self.post(data=xml_payload, headers=headers)
        xml_response = response.get("raw_response", None) if success else None
        disposition_list = []
        if success and xml_response:
            try:
                root = ET.fromstring(xml_response)
                for data_elem in root.findall(".//data"):
                    data_dict = {child.tag: child.text for child in data_elem}
                    disposition_list.append(data_dict)
                logging.info(f"[ XTRACK ] get_dispositions parsed data: {len(disposition_list)} items")
            except Exception as e:
                logging.error(f"[ XTRACK ] XML parsing error: {e}")
                return False, {"error": "XML parsing failed", "detail": str(e)}
        else:
            logging.info(f"[ XTRACK ] get_dispositions response: {xml_response}")
        return success, disposition_list if success else response

    async def get_groups(self):
        xml_payload = """
        <msg>
            <command>GetGroup</command>
            <terminal>ERP</terminal>
        </msg>
        """
        headers = {"Content-Type": "application/xml"}
        success, response = await self.post(data=xml_payload, headers=headers)
        xml_response = response.get("raw_response", None) if success else None
        group_list = []
        if success and xml_response:
            try:
                root = ET.fromstring(xml_response)
                for data_elem in root.findall(".//data"):
                    data_dict = {child.tag: child.text for child in data_elem}
                    group_list.append(data_dict)
                logging.info(f"[ XTRACK ] get_groups parsed data: {len(group_list)} items")
            except Exception as e:
                logging.error(f"[ XTRACK ] XML parsing error: {e}")
                return False, {"error": "XML parsing failed", "detail": str(e)}
        else:
            logging.info(f"[ XTRACK ] get_groups response: {xml_response}")
        return success, group_list if success else response

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
        if success and xml_response:
            try:
                root = ET.fromstring(xml_response)
                for data_elem in root.findall(".//data"):
                    data_dict = {child.tag: child.text for child in data_elem}
                    location_list.append(data_dict)
                logging.info(f"[ XTRACK ] get_locations parsed data: {len(location_list)} items")
            except Exception as e:
                logging.error(f"[ XTRACK ] XML parsing error: {e}")
                return False, {"error": "XML parsing failed", "detail": str(e)}
        else:
            logging.info(f"[ XTRACK ] get_locations response: {xml_response}")
        return success, location_list if success else response

    async def get_products(self):
        xml_payload = """
        <msg>
            <command>GetProduct</command>
            <terminal>ERP</terminal>
        </msg>
        """
        headers = {"Content-Type": "application/xml"}
        success, response = await self.post(data=xml_payload, headers=headers)
        xml_response = response.get("raw_response", None) if success else None
        product_list = []
        if success and xml_response:
            try:
                root = ET.fromstring(xml_response)
                for data_elem in root.findall(".//data"):
                    data_dict = {child.tag: child.text for child in data_elem}
                    product_list.append(data_dict)
                logging.info(f"[ XTRACK ] get_products parsed data: {len(product_list)} items")
            except Exception as e:
                logging.error(f"[ XTRACK ] XML parsing error: {e}")
                return False, {"error": "XML parsing failed", "detail": str(e)}
        else:
            logging.info(f"[ XTRACK ] get_products response: {xml_response}")
        return success, product_list if success else response

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
        if success and xml_response:
            try:
                root = ET.fromstring(xml_response)
                for data_elem in root.findall(".//data"):
                    data_dict = {child.tag: child.text for child in data_elem}
                    data_list.append(data_dict)
                logging.info(f"[ XTRACK ] get_objects parsed data: {len(data_list)} items")
            except Exception as e:
                logging.error(f"[ XTRACK ] XML parsing error: {e}")
                return False, {"error": "XML parsing failed", "detail": str(e)}
        else:
            logging.info(f"[ XTRACK ] get_objects response: {xml_response}")
        return success, data_list if success else response

    async def get_object_by_idcode(self, idcode: str | list):
        if not isinstance(idcode, list):
            idcode = [idcode]
        xml_payload = f"""
        <msg>
            <command>GetObject</command>
            <terminal>ERP</terminal>
            <data><object>
                {"".join([f"<IDCODE>{ic}</IDCODE>" for ic in idcode])}
            </object></data>
        </msg>
        """
        headers = {"Content-Type": "application/xml"}
        success, response = await self.post(data=xml_payload, headers=headers)
        xml_response = response.get("raw_response", None) if success else None
        data_list = []
        if success and xml_response:
            try:
                root = ET.fromstring(xml_response)
                for data_elem in root.findall(".//data"):
                    data_dict = {child.tag: child.text for child in data_elem}
                    data_list.append(data_dict)
                logging.info(f"[ XTRACK ] get_object_by_idcode parsed data: {len(data_list)} items")
            except Exception as e:
                logging.error(f"[ XTRACK ] XML parsing error: {e}")
                return False, {"error": "XML parsing failed", "detail": str(e)}
        else:
            logging.info(f"[ XTRACK ] get_object_by_idcode response: {xml_response}")
        return success, data_list if success else response

    async def get_identifications(self):
        xml_payload = """
        <msg>
            <command>GetIdentification</command>
            <terminal>ERP</terminal>
        </msg>
        """
        headers = {"Content-Type": "application/xml"}
        success, response = await self.post(data=xml_payload, headers=headers)
        xml_response = response.get("raw_response", None) if success else None
        identification_list = []
        if success and xml_response:
            try:
                root = ET.fromstring(xml_response)
                for data_elem in root.findall(".//data"):
                    data_dict = {child.tag: child.text for child in data_elem}
                    identification_list.append(data_dict)
                logging.info(f"[ XTRACK ] get_identifications parsed data: {len(identification_list)} items")
            except Exception as e:
                logging.error(f"[ XTRACK ] XML parsing error: {e}")
                return False, {"error": "XML parsing failed", "detail": str(e)}
        else:
            logging.info(f"[ XTRACK ] get_identifications response: {xml_response}")
        return success, identification_list if success else response

    async def get_users(self):
        xml_payload = """
        <msg>
            <command>GetUser</command>
            <terminal>ERP</terminal>
        </msg>
        """
        headers = {"Content-Type": "application/xml"}
        success, response = await self.post(data=xml_payload, headers=headers)
        xml_response = response.get("raw_response", None) if success else None
        user_list = []
        if success and xml_response:
            try:
                root = ET.fromstring(xml_response)
                for data_elem in root.findall(".//data"):
                    data_dict = {child.tag: child.text for child in data_elem}
                    user_list.append(data_dict)
                logging.info(f"[ XTRACK ] get_users parsed data: {len(user_list)} items")
            except Exception as e:
                logging.error(f"[ XTRACK ] XML parsing error: {e}")
                return False, {"error": "XML parsing failed", "detail": str(e)}
        else:
            logging.info(f"[ XTRACK ] get_users response: {xml_response}")
        return success, user_list if success else response

    async def get_object_by_epc(self, epc: str | list):
        if not isinstance(epc, list):
            epc = [epc]

        xml_payload = f"""
        <msg>
            <command>GetObject</command>
            <terminal>ERP</terminal>
            <data>
                {"".join([f"<object><EPC>{e.upper()}</EPC></object>" for e in epc])}
            </data>
        </msg>
        """
        headers = {"Content-Type": "application/xml"}
        success, response = await self.post(data=xml_payload, headers=headers)
        xml_response = response.get("raw_response", None) if success else None
        parsed = []
        if success and xml_response:
            try:
                root = ET.fromstring(xml_response)

                def _elem_to_dict(elem):
                    if elem is None:
                        return None
                    d = {}
                    for child in elem:
                        tag = child.tag.split("}")[-1].lower()
                        # recurse for nested elements
                        if list(child):
                            sub = _elem_to_dict(child)
                            if tag in d:
                                if isinstance(d[tag], list):
                                    d[tag].append(sub)
                                else:
                                    d[tag] = [d[tag], sub]
                            else:
                                d[tag] = sub
                        else:
                            text = child.text.strip() if child.text and child.text.strip() else None
                            if tag in d:
                                if isinstance(d[tag], list):
                                    d[tag].append(text)
                                else:
                                    d[tag] = [d[tag], text]
                            else:
                                d[tag] = text
                    return d

                # There can be multiple <data> elements; handle each one.
                for data_elem in root.findall(".//data"):
                    # prefer explicit <object> children
                    objects = data_elem.findall("object")
                    if objects:
                        for obj in objects:
                            od = _elem_to_dict(obj)
                            if od is not None:
                                parsed.append(od)
                        continue

                    # fallback to <product> children
                    products = data_elem.findall("product")
                    if products:
                        for prod in products:
                            pd = _elem_to_dict(prod)
                            if pd is not None:
                                parsed.append(pd)
                        continue

                    # otherwise treat the <data> element itself as a record
                    dd = _elem_to_dict(data_elem)
                    if dd is not None:
                        parsed.append(dd)

                logging.info(f"[ XTRACK ] get_object_by_epc parsed data: {parsed}")
            except Exception as e:
                logging.error(f"[ XTRACK ] XML parsing error: {e}")
                return False, {"error": "XML parsing failed", "detail": str(e)}
        else:
            logging.info(f"[ XTRACK ] get_object_by_epc response: {xml_response}")

        # Convert parsed list to a dict keyed by identification.idcode (fallbacks)
        if success:
            mapped = {}
            for v in parsed:
                if not isinstance(v, dict):
                    continue
                key = None
                ident = v.get("identification")
                if isinstance(ident, dict):
                    key = ident.get("idcode") or ident.get("id")
                if not key:
                    key = v.get("idcode") or v.get("id") or v.get("product_id") or v.get("productid")
                if key is None:
                    logging.debug(f"[ XTRACK ] skipping object without idkey: {v}")
                    continue
                mapped[str(key)] = v

            logging.info(f"[ XTRACK ] get_object_by_epc mapped keys: {list(mapped.keys())}")
            return True, mapped

        return success, response

    async def get_idcode_from_epc(self, epc: str):
        # reuse get_object_by_epc and return only the idcode (prefers identification.idcode)
        success, data = await self.get_object_by_epc(epc)
        if not success:
            return success, data

        idcode = data.get(epc, {}).get("idcode")

        logging.info(f"[ XTRACK ] get_idcode_from_epc resolved IDCODE: {idcode}")
        return True, idcode

    # REGISTER METHODS
    async def register_category(self, category_name: str):
        xml_payload = f"""
        <msg>
            <command>ImportCategory</command>
            <terminal>ERP</terminal>
            <data>
                <category>
                    <NAME>{category_name}</NAME>
                </category>
            </data>
        </msg>
        """
        headers = {"Content-Type": "application/xml"}
        success, response = await self.post(data=xml_payload, headers=headers)
        logging.info(f"[ XTRACK ] register_category response: {response}")
        return success, response

    async def register_condition(self, condition_name: str):
        xml_payload = f"""
        <msg>
            <command>ImportCondition</command>
            <terminal>ERP</terminal>
            <data>
                <condition>
                    <NAME>{condition_name}</NAME>
                </condition>
            </data>
        </msg>
        """
        headers = {"Content-Type": "application/xml"}
        success, response = await self.post(data=xml_payload, headers=headers)
        logging.info(f"[ XTRACK ] register_condition response: {response}")
        return success, response

    async def register_cost_center(self, cost_center_name: str):
        xml_payload = f"""
        <msg>
            <command>ImportCostCenter</command>
            <terminal>ERP</terminal>
            <data>
                <costcenter>
                    <NAME>{cost_center_name}</NAME>
                </costcenter>
            </data>
        </msg>
        """
        headers = {"Content-Type": "application/xml"}
        success, response = await self.post(data=xml_payload, headers=headers)
        logging.info(f"[ XTRACK ] register_cost_center response: {response}")
        return success, response

    async def register_custodian(self, custodian_name: str, custodian_description: str = ""):
        xml_payload = f"""
        <msg>
            <command>ImportCustodian</command>
            <terminal>ERP</terminal>
            <data>
                <custodian>
                    <NAME>{custodian_name}</NAME>
                    <DESCRIPTION>{custodian_description}</DESCRIPTION>
                </custodian>
            </data>
        </msg>
        """
        headers = {"Content-Type": "application/xml"}
        success, response = await self.post(data=xml_payload, headers=headers)
        logging.info(f"[ XTRACK ] register_custodian response: {response}")
        return success, response

    async def register_department(self, department_name: str):
        xml_payload = f"""
        <msg>
            <command>ImportDepartment</command>
            <terminal>ERP</terminal>
            <data>
                <department>
                    <NAME>{department_name}</NAME>
                </department>
            </data>
        </msg>
        """
        headers = {"Content-Type": "application/xml"}
        success, response = await self.post(data=xml_payload, headers=headers)
        logging.info(f"[ XTRACK ] register_department response: {response}")
        return success, response

    async def register_disposal(self, disposal_name: str):
        xml_payload = f"""
        <msg>
            <command>ImportDisposal</command>
            <terminal>ERP</terminal>
            <data>
                <disposal>
                    <NAME>{disposal_name}</NAME>
                </disposal>
            </data>
        </msg>
        """
        headers = {"Content-Type": "application/xml"}
        success, response = await self.post(data=xml_payload, headers=headers)
        logging.info(f"[ XTRACK ] register_disposal response: {response}")
        return success, response

    async def register_disposition(self, disposition_name: str, epc: str):
        xml_payload = f"""
        <msg>
            <command>ImportDisposition</command>
            <terminal>ERP</terminal>
            <data>
                <disposition>
                    <NAME>{disposition_name}</NAME>
                    <EPC_URI>{epc}</EPC_URI>
                </disposition>
            </data>
        </msg>
        """
        headers = {"Content-Type": "application/xml"}
        success, response = await self.post(data=xml_payload, headers=headers)
        logging.info(f"[ XTRACK ] register_disposition response: {response}")
        return success, response

    async def register_group(self, group_name: str):
        xml_payload = f"""
        <msg>
            <command>ImportGroup</command>
            <terminal>ERP</terminal>
            <data>
                <group>
                    <NAME>{group_name}</NAME>
                </group>
            </data>
        </msg>
        """
        headers = {"Content-Type": "application/xml"}
        success, response = await self.post(data=xml_payload, headers=headers)
        logging.info(f"[ XTRACK ] register_group response: {response}")
        return success, response

    async def register_location(
        self,
        location_name: str,
        allocable: bool = True,
        idetype1: str = "",
        idecode1: str = "",
        idetype2: str = "",
        idecode2: str = "",
        idetype3: str = "",
        idecode3: str = "",
        idetype4: str = "",
        idecode4: str = "",
    ):
        allocable_value = "1" if allocable else "0"
        xml_payload = f"""
        <msg>
            <command>ImportLocation</command>
            <terminal>ERP</terminal>
            <data>
                <location>
                    <NAME>{location_name}</NAME>
                    <ALLOCABLE>{allocable_value}</ALLOCABLE>
                    <IDETYPE1>{idetype1}</IDETYPE1>
                    <IDECODE1>{idecode1}</IDECODE1>
                    <IDETYPE2>{idetype2}</IDETYPE2>
                    <IDECODE2>{idecode2}</IDECODE2>
                    <IDETYPE3>{idetype3}</IDETYPE3>
                    <IDECODE3>{idecode3}</IDECODE3>
                    <IDETYPE4>{idetype4}</IDETYPE4>
                    <IDECODE4>{idecode4}</IDECODE4>
                </location>
            </data>
        </msg>
        """
        headers = {"Content-Type": "application/xml"}
        success, response = await self.post(data=xml_payload, headers=headers)
        logging.info(f"[ XTRACK ] register_location response: {response}")
        return success, response

    async def register_product(
        self,
        idcode: str,
        description: str,
        category: str,
        gs1ref: str = "",
        container: int = 0,
        usrdata1: str = "",
        usrdata2: str = "",
        usrdata3: str = "",
        usrdata4: str = "",
        usrdata5: str = "",
        usrdata6: str = "",
        usrdata7: str = "",
        usrdata8: str = "",
        usrdata9: str = "",
        idetype1: str = "",
        idecode1: str = "",
        idetype2: str = "",
        idecode2: str = "",
        idetype3: str = "",
        idecode3: str = "",
        idetype4: str = "",
        idecode4: str = "",
        imagefile: str = "",
    ):
        xml_payload = f"""
        <msg>
            <command>ImportItemModel</command>
            <terminal>ERP</terminal>
            <data>
                <itemmodel>
                    <IDCODE>{idcode}</IDCODE>
                    <DESCRIPTION>{description}</DESCRIPTION>
                    <CATEGORY>{category}</CATEGORY>
                    <GS1REF>{gs1ref}</GS1REF>
                    <CONTAINER>{container}</CONTAINER>
                    <USRDATA1>{usrdata1}</USRDATA1>
                    <USRDATA2>{usrdata2}</USRDATA2>
                    <USRDATA3>{usrdata3}</USRDATA3>
                    <USRDATA4>{usrdata4}</USRDATA4>
                    <USRDATA5>{usrdata5}</USRDATA5>
                    <USRDATA6>{usrdata6}</USRDATA6>
                    <USRDATA7>{usrdata7}</USRDATA7>
                    <USRDATA8>{usrdata8}</USRDATA8>
                    <USRDATA9>{usrdata9}</USRDATA9>
                    <IDETYPE1>{idetype1}</IDETYPE1>
                    <IDECODE1>{idecode1}</IDECODE1>
                    <IDETYPE2>{idetype2}</IDETYPE2>
                    <IDECODE2>{idecode2}</IDECODE2>
                    <IDETYPE3>{idetype3}</IDETYPE3>
                    <IDECODE3>{idecode3}</IDECODE3>
                    <IDETYPE4>{idetype4}</IDETYPE4>
                    <IDECODE4>{idecode4}</IDECODE4>
                    <IMAGEFILE>{imagefile}</IMAGEFILE>
                </itemmodel>
            </data>
        </msg>
        """
        headers = {"Content-Type": "application/xml"}
        success, response = await self.post(data=xml_payload, headers=headers)
        logging.info(f"[ XTRACK ] register_product response: {response}")
        return success, response

    async def register_object(
        self,
        active: int,
        idcode: str,
        description: str,
        serialnumber: str,
        quantity: int,
        itemmodel_idcode: str,
        department_name: str,
        condition_name: str,
        disposition_name: str,
        location_name: str,
        homelocation_name: str = "",
        group_name: str = "",
        custodian_name: str = "",
        disposal_name: str = "",
        costcenter_name: str = "",
        container_idcode: str = "",
        latitude: str = "",
        longitude: str = "",
        usrdata1: str = "",
        usrdata2: str = "",
        usrdata3: str = "",
        usrdata4: str = "",
        usrdata5: str = "",
        usrdata6: str = "",
        usrdata7: str = "",
        usrdata8: str = "",
        usrdata9: str = "",
        idetype1: str = "BARCODE",
        idecode1: str = "",
        idetype2: str = "RFID",
        idecode2: str = "",
        idetype3: str = "",
        idecode3: str = "",
        idetype4: str = "",
        idecode4: str = "",
        imagefile: str = "",
    ):
        xml_payload = f"""
        <msg>
            <command>ImportObject</command>
            <terminal>ERP</terminal>
            <data>
                <object>
                    <ACTIVE>{active}</ACTIVE>
                    <IDCODE>{idcode}</IDCODE>
                    <DESCRIPTION>{description}</DESCRIPTION>
                    <SERIALNUMBER>{serialnumber}</SERIALNUMBER>
                    <QUANTITY>{quantity}</QUANTITY>
                    <ITEMMODEL_IDCODE>{itemmodel_idcode}</ITEMMODEL_IDCODE>
                    <DEPARTMENT_NAME>{department_name}</DEPARTMENT_NAME>
                    <CONDITION_NAME>{condition_name}</CONDITION_NAME>
                    <DISPOSITION_NAME>{disposition_name}</DISPOSITION_NAME>
                    <LOCATION_NAME>{location_name}</LOCATION_NAME>
                    <HOMELOCATION_NAME>{homelocation_name}</HOMELOCATION_NAME>
                    <GROUP_NAME>{group_name}</GROUP_NAME>
                    <CUSTODIAN_NAME>{custodian_name}</CUSTODIAN_NAME>
                    <DISPOSAL_NAME>{disposal_name}</DISPOSAL_NAME>
                    <COSTCENTER_NAME>{costcenter_name}</COSTCENTER_NAME>
                    <CONTAINER_IDCODE>{container_idcode}</CONTAINER_IDCODE>
                    <LATITUDE>{latitude}</LATITUDE>
                    <LONGITUDE>{longitude}</LONGITUDE>
                    <USRDATA1>{usrdata1}</USRDATA1>
                    <USRDATA2>{usrdata2}</USRDATA2>
                    <USRDATA3>{usrdata3}</USRDATA3>
                    <USRDATA4>{usrdata4}</USRDATA4>
                    <USRDATA5>{usrdata5}</USRDATA5>
                    <USRDATA6>{usrdata6}</USRDATA6>
                    <USRDATA7>{usrdata7}</USRDATA7>
                    <USRDATA8>{usrdata8}</USRDATA8>
                    <USRDATA9>{usrdata9}</USRDATA9>
                    <IDETYPE1>{idetype1}</IDETYPE1>
                    <IDECODE1>{idecode1}</IDECODE1>
                    <IDETYPE2>{idetype2}</IDETYPE2>
                    <IDECODE2>{idecode2}</IDECODE2>
                    <IDETYPE3>{idetype3}</IDETYPE3>
                    <IDECODE3>{idecode3}</IDECODE3>
                    <IDETYPE4>{idetype4}</IDETYPE4>
                    <IDECODE4>{idecode4}</IDECODE4>
                    <IMAGEFILE>{imagefile}</IMAGEFILE>
                </object>
            </data>
        </msg>
        """
        headers = {"Content-Type": "application/xml"}
        success, response = await self.post(data=xml_payload, headers=headers)
        logging.info(f"[ XTRACK ] register_object response: {response}")
        return success, response

    async def register_objects_bulk(self, objects: list):
        """
        Register multiple objects in bulk.

        This method constructs an XML payload that includes one or more
        `<object>` entries and sends it to the Xtrack API using the
        instance `post` helper.

        Parameters:
            objects (list): A list of dictionaries where each dictionary
                represents an object to import. Each dictionary's keys are
                used as XML tag names and values as the tag text.

        Returns:
            tuple[bool, dict]: A tuple `(success, response)` where `success`
            is True when the HTTP request completed successfully. `response`
            is the parsed JSON response when available or a dict containing
            a `raw_response` key with the raw response text.
        """
        expected_fields = {
            "ACTIVE": 1,
            "IDCODE": "",
            "DESCRIPTION": "",
            "SERIALNUMBER": "",
            "QUANTITY": 1,
            "ITEMMODEL_IDCODE": "",
            "DEPARTMENT_NAME": "",
            "CONDITION_NAME": "",
            "DISPOSITION_NAME": "",
            "LOCATION_NAME": "",
            "HOMELOCATION_NAME": "",
            "GROUP_NAME": "",
            "CUSTODIAN_NAME": "",
            "DISPOSAL_NAME": "",
            "COSTCENTER_NAME": "",
            "CONTAINER_IDCODE": "",
            "LATITUDE": "",
            "LONGITUDE": "",
            "USRDATA1": "",
            "USRDATA2": "",
            "USRDATA3": "",
            "USRDATA4": "",
            "USRDATA5": "",
            "USRDATA6": "",
            "USRDATA7": "",
            "USRDATA8": "",
            "USRDATA9": "",
            "IDETYPE1": "BARCODE",
            "IDECODE1": "",
            "IDETYPE2": "RFID",
            "IDECODE2": "",
            "IDETYPE3": "",
            "IDECODE3": "",
            "IDETYPE4": "",
            "IDECODE4": "",
            "IMAGEFILE": "",
        }

        # Normalize incoming object keys to uppercase so they match expected fields
        objects = [{k.upper(): v for k, v in obj.items()} for obj in objects]

        def _escape(field, value):
            # Use the default from expected_fields when value is None or
            # an empty string; preserve falsy but meaningful values like 0.
            default = expected_fields.get(field, "")
            if value is None or (isinstance(value, str) and value == ""):
                val = default
            else:
                val = value
            return "" if val is None else str(val)

        # Build XML by iterating the canonical expected_fields order for each object
        objects_xml = []
        for obj in objects:
            field_elems = "".join(f"<{field}>{_escape(field, obj.get(field))}</{field}>" for field in expected_fields)
            objects_xml.append(f"<object>{field_elems}</object>")

        xml_payload = f"""
        <msg>
            <command>ImportObject</command>
            <terminal>ERP</terminal>
            <data>
                {"".join(objects_xml)}
            </data>
        </msg>
        """
        headers = {"Content-Type": "application/xml"}
        success, response = await self.post(data=xml_payload, headers=headers)
        logging.info(f"[ XTRACK ] register_objects_bulk response: {response}")
        return success, response

    # DELETE METHODS
    async def delete_category(self, category_name: str):
        xml_payload = f"""
        <msg>
            <command>DeleteCategory</command>
            <terminal>ERP</terminal>
            <data>
                <category>
                    <NAME>{category_name}</NAME>
                </category>
            </data>
        </msg>
        """
        headers = {"Content-Type": "application/xml"}
        success, response = await self.post(data=xml_payload, headers=headers)
        logging.info(f"[ XTRACK ] delete_category response: {response}")
        return success, response

    async def delete_all_categories(self):
        xml_payload = """
        <msg>
            <command>DeleteAllCategory</command>
            <terminal>ERP</terminal>
        </msg>
        """
        headers = {"Content-Type": "application/xml"}
        success, response = await self.post(data=xml_payload, headers=headers)
        logging.info(f"[ XTRACK ] delete_all_categories response: {response}")
        return success, response

    async def delete_condition(self, condition_name: str):
        xml_payload = f"""
        <msg>
            <command>DeleteCondition</command>
            <terminal>ERP</terminal>
            <data>
                <condition>
                    <NAME>{condition_name}</NAME>
                </condition>
            </data>
        </msg>
        """
        headers = {"Content-Type": "application/xml"}
        success, response = await self.post(data=xml_payload, headers=headers)
        logging.info(f"[ XTRACK ] delete_condition response: {response}")
        return success, response

    async def delete_all_conditions(self):
        xml_payload = """
        <msg>
            <command>DeleteAllCondition</command>
            <terminal>ERP</terminal>
        </msg>
        """
        headers = {"Content-Type": "application/xml"}
        success, response = await self.post(data=xml_payload, headers=headers)
        logging.info(f"[ XTRACK ] delete_all_conditions response: {response}")
        return success, response

    async def delete_cost_center(self, cost_center_name: str):
        xml_payload = f"""
        <msg>
            <command>DeleteCostCenter</command>
            <terminal>ERP</terminal>
            <data>
                <costcenter>
                    <NAME>{cost_center_name}</NAME>
                </costcenter>
            </data>
        </msg>
        """
        headers = {"Content-Type": "application/xml"}
        success, response = await self.post(data=xml_payload, headers=headers)
        logging.info(f"[ XTRACK ] delete_cost_center response: {response}")
        return success, response

    async def delete_all_cost_centers(self):
        xml_payload = """
        <msg>
            <command>DeleteAllCostCenter</command>
            <terminal>ERP</terminal>
        </msg>
        """
        headers = {"Content-Type": "application/xml"}
        success, response = await self.post(data=xml_payload, headers=headers)
        logging.info(f"[ XTRACK ] delete_all_cost_centers response: {response}")
        return success, response

    async def delete_custodian(self, custodian_name: str):
        xml_payload = f"""
        <msg>
            <command>DeleteCustodian</command>
            <terminal>ERP</terminal>
            <data>
                <custodian>
                    <NAME>{custodian_name}</NAME>
                </custodian>
            </data>
        </msg>
        """
        headers = {"Content-Type": "application/xml"}
        success, response = await self.post(data=xml_payload, headers=headers)
        logging.info(f"[ XTRACK ] delete_custodian response: {response}")
        return success, response

    async def delete_all_custodians(self):
        xml_payload = """
        <msg>
            <command>DeleteAllCustodian</command>
            <terminal>ERP</terminal>
        </msg>
        """
        headers = {"Content-Type": "application/xml"}
        success, response = await self.post(data=xml_payload, headers=headers)
        logging.info(f"[ XTRACK ] delete_all_custodians response: {response}")
        return success, response

    async def delete_department(self, department_name: str):
        xml_payload = f"""
        <msg>
            <command>DeleteDepartment</command>
            <terminal>ERP</terminal>
            <data>
                <department>
                    <NAME>{department_name}</NAME>
                </department>
            </data>
        </msg>
        """
        headers = {"Content-Type": "application/xml"}
        success, response = await self.post(data=xml_payload, headers=headers)
        logging.info(f"[ XTRACK ] delete_department response: {response}")
        return success, response

    async def delete_all_departments(self):
        xml_payload = """
        <msg>
            <command>DeleteAllDepartment</command>
            <terminal>ERP</terminal>
        </msg>
        """
        headers = {"Content-Type": "application/xml"}
        success, response = await self.post(data=xml_payload, headers=headers)
        logging.info(f"[ XTRACK ] delete_all_departments response: {response}")
        return success, response

    async def delete_disposal(self, disposal_name: str):
        xml_payload = f"""
        <msg>
            <command>DeleteDisposal</command>
            <terminal>ERP</terminal>
            <data>
                <disposal>
                    <NAME>{disposal_name}</NAME>
                </disposal>
            </data>
        </msg>
        """
        headers = {"Content-Type": "application/xml"}
        success, response = await self.post(data=xml_payload, headers=headers)
        logging.info(f"[ XTRACK ] delete_disposal response: {response}")
        return success, response

    async def delete_all_disposals(self):
        xml_payload = """
        <msg>
            <command>DeleteAllDisposal</command>
            <terminal>ERP</terminal>
        </msg>
        """
        headers = {"Content-Type": "application/xml"}
        success, response = await self.post(data=xml_payload, headers=headers)
        logging.info(f"[ XTRACK ] delete_all_disposals response: {response}")
        return success, response

    async def delete_disposition(self, disposition_name: str, epc_uri: str = ""):
        xml_payload = f"""
        <msg>
            <command>DeleteDisposition</command>
            <terminal>ERP</terminal>
            <data>
                <disposition>
                    <NAME>{disposition_name}</NAME>
                    <EPC_URI>{epc_uri}</EPC_URI>
                </disposition>
            </data>
        </msg>
        """
        headers = {"Content-Type": "application/xml"}
        success, response = await self.post(data=xml_payload, headers=headers)
        logging.info(f"[ XTRACK ] delete_disposition response: {response}")
        return success, response

    async def delete_all_dispositions(self):
        xml_payload = """
        <msg>
            <command>DeleteAllDisposition</command>
            <terminal>ERP</terminal>
        </msg>
        """
        headers = {"Content-Type": "application/xml"}
        success, response = await self.post(data=xml_payload, headers=headers)
        logging.info(f"[ XTRACK ] delete_all_dispositions response: {response}")
        return success, response

    async def delete_group(self, group_name: str):
        xml_payload = f"""
        <msg>
            <command>DeleteGroup</command>
            <terminal>ERP</terminal>
            <data>
                <group>
                    <NAME>{group_name}</NAME>
                </group>
            </data>
        </msg>
        """
        headers = {"Content-Type": "application/xml"}
        success, response = await self.post(data=xml_payload, headers=headers)
        logging.info(f"[ XTRACK ] delete_group response: {response}")
        return success, response

    async def delete_all_groups(self):
        xml_payload = """
        <msg>
            <command>DeleteAllGroup</command>
            <terminal>ERP</terminal>
        </msg>
        """
        headers = {"Content-Type": "application/xml"}
        success, response = await self.post(data=xml_payload, headers=headers)
        logging.info(f"[ XTRACK ] delete_all_groups response: {response}")
        return success, response

    async def delete_location(self, location_name: str):
        xml_payload = f"""
        <msg>
            <command>DeleteLocation</command>
            <terminal>ERP</terminal>
            <data>
                <location>
                    <NAME>{location_name}</NAME>
                </location>
            </data>
        </msg>
        """
        headers = {"Content-Type": "application/xml"}
        success, response = await self.post(data=xml_payload, headers=headers)
        logging.info(f"[ XTRACK ] delete_location response: {response}")
        return success, response

    async def delete_all_locations(self):
        xml_payload = """
        <msg>
            <command>DeleteAllLocation</command>
            <terminal>ERP</terminal>
        </msg>
        """
        headers = {"Content-Type": "application/xml"}
        success, response = await self.post(data=xml_payload, headers=headers)
        logging.info(f"[ XTRACK ] delete_all_locations response: {response}")
        return success, response

    async def delete_item_model(self, idcode: str):
        xml_payload = f"""
        <msg>
            <command>DeleteItemModel</command>
            <terminal>ERP</terminal>
            <data>
                <itemmodel>
                    <IDCODE>{idcode}</IDCODE>
                </itemmodel>
            </data>
        </msg>
        """
        headers = {"Content-Type": "application/xml"}
        success, response = await self.post(data=xml_payload, headers=headers)
        logging.info(f"[ XTRACK ] delete_item_model response: {response}")
        return success, response

    async def delete_all_item_models(self):
        xml_payload = """
        <msg>
            <command>DeleteAllItemModel</command>
            <terminal>ERP</terminal>
        </msg>
        """
        headers = {"Content-Type": "application/xml"}
        success, response = await self.post(data=xml_payload, headers=headers)
        logging.info(f"[ XTRACK ] delete_all_item_models response: {response}")
        return success, response

    async def delete_object(self, idcode: str):
        xml_payload = f"""
        <msg>
            <command>DeleteObject</command>
            <terminal>ERP</terminal>
            <data>
                <object>
                    <IDCODE>{idcode}</IDCODE>
                </object>
            </data>
        </msg>
        """
        headers = {"Content-Type": "application/xml"}
        success, response = await self.post(data=xml_payload, headers=headers)
        logging.info(f"[ XTRACK ] delete_object response: {response}")
        return success, response

    async def delete_all_objects(self):
        xml_payload = """
        <msg>
            <command>DeleteAllObject</command>
            <terminal>ERP</terminal>
        </msg>
        """
        headers = {"Content-Type": "application/xml"}
        success, response = await self.post(data=xml_payload, headers=headers)
        logging.info(f"[ XTRACK ] delete_all_objects response: {response}")
        return success, response

    # MOVE METHODS
    async def move_object(self, idcode: str, location_id: str):
        xml_payload = f"""
        <msg>
            <command>MoveLocation</command>
            <terminal>SAPext</terminal>
            <data>
                <object>{idcode}</object>
                <location>{location_id}</location>
            </data>
        </msg>
        """
        headers = {"Content-Type": "application/xml"}
        success, response = await self.post(data=xml_payload, headers=headers)
        logging.info(f"[ XTRACK ] move_object response: {response}")
        return success, response

    async def move_objects_bulk(self, moves: list):
        """
        Move multiple objects to new locations in bulk.

        Builds an XML payload containing pairs of `<object>` and
        `<location>` tags for each move instruction and sends it via the
        instance `post` helper.

        Parameters:
            moves (list): A list of dicts with keys `idcode` and
                `location_id` describing each move.

        Returns:
            tuple[bool, dict]: A tuple `(success, response)` returned from
            the underlying `post` call. `success` is True on HTTP success
            and `response` contains the parsed response or raw text.
        """
        xml_payload = f"""
        <msg>
            <command>MoveLocation</command>
            <terminal>SAPext</terminal>
                {"".join([f"<data><object>{move.get('idcode')}</object><location>{move.get('location_id')}</location></data>" for move in moves])}
        </msg>
        """
        headers = {"Content-Type": "application/xml"}
        success, response = await self.post(data=xml_payload, headers=headers)
        logging.info(f"[ XTRACK ] move_objects_bulk response: {response}")
        return success, response

    async def move_condition(self, idcode: str, condition: str):
        xml_payload = f"""
        <msg>
            <command>MoveCondition</command>
            <terminal>SAPext</terminal>
            <data>
                <object>{idcode}</object>
                <condition>{condition}</condition>
            </data>
        </msg>
        """
        headers = {"Content-Type": "application/xml"}
        success, response = await self.post(data=xml_payload, headers=headers)
        logging.info(f"[ XTRACK ] move_condition response: {response}")
        return success, response

    async def move_disposition(self, idcode: str, disposition: str):
        xml_payload = f"""
        <msg>
            <command>MoveDisposition</command>
            <terminal>SAPext</terminal>
            <data>
                <object>{idcode}</object>
                <disposition>{disposition}</disposition>
            </data>
        </msg>
        """
        headers = {"Content-Type": "application/xml"}
        success, response = await self.post(data=xml_payload, headers=headers)
        logging.info(f"[ XTRACK ] move_disposition response: {response}")
        return success, response

    async def move_custodian(self, idcode: str, custodian: str):
        xml_payload = f"""
        <msg>
            <command>MoveCustodian</command>
            <terminal>SAPext</terminal>
            <data>
                <object>{idcode}</object>
                <custodian>{custodian}</custodian>
            </data>
        </msg>
        """
        headers = {"Content-Type": "application/xml"}
        success, response = await self.post(data=xml_payload, headers=headers)
        logging.info(f"[ XTRACK ] move_custodian response: {response}")
        return success, response

    async def move_cost_center(self, idcode: str, costcenter: str):
        xml_payload = f"""
        <msg>
            <command>MoveCostCenter</command>
            <terminal>SAPext</terminal>
            <data>
                <object>{idcode}</object>
                <costcenter>{costcenter}</costcenter>
            </data>
        </msg>
        """
        headers = {"Content-Type": "application/xml"}
        success, response = await self.post(data=xml_payload, headers=headers)
        logging.info(f"[ XTRACK ] move_cost_center response: {response}")
        return success, response

    async def move_group(self, idcode: str, group: str):
        xml_payload = f"""
        <msg>
            <command>MoveGroup</command>
            <terminal>SAPext</terminal>
            <data>
                <object>{idcode}</object>
                <group>{group}</group>
            </data>
        </msg>
        """
        headers = {"Content-Type": "application/xml"}
        success, response = await self.post(data=xml_payload, headers=headers)
        logging.info(f"[ XTRACK ] move_group response: {response}")
        return success, response

    async def move_disposal(self, idcode: str, disposal: str):
        xml_payload = f"""
        <msg>
            <command>MoveDisposal</command>
            <terminal>SAPext</terminal>
            <data>
                <object>{idcode}</object>
                <disposal>{disposal}</disposal>
            </data>
        </msg>
        """
        headers = {"Content-Type": "application/xml"}
        success, response = await self.post(data=xml_payload, headers=headers)
        logging.info(f"[ XTRACK ] move_disposal response: {response}")
        return success, response

    async def move_department(self, idcode: str, department: str):
        xml_payload = f"""
        <msg>
            <command>MoveDepartment</command>
            <terminal>SAPext</terminal>
            <data>
                <object>{idcode}</object>
                <department>{department}</department>
            </data>
        </msg>
        """
        headers = {"Content-Type": "application/xml"}
        success, response = await self.post(data=xml_payload, headers=headers)
        logging.info(f"[ XTRACK ] move_department response: {response}")
        return success, response

    async def update_usrdata(
        self,
        idcode: str,
        usrdata1: str = "",
        usrdata2: str = "",
        usrdata3: str = "",
        usrdata4: str = "",
        usrdata5: str = "",
        usrdata6: str = "",
        usrdata7: str = "",
        usrdata8: str = "",
        usrdata9: str = "",
    ):
        usr_values = [usrdata1, usrdata2, usrdata3, usrdata4, usrdata5, usrdata6, usrdata7, usrdata8, usrdata9]
        data_fields = "".join(
            f"<USRDATA{i + 1}>{usr_values[i]}</USRDATA{i + 1}>" for i in range(len(usr_values)) if usr_values[i] != ""
        )
        xml_payload = f"""
        <msg>
            <command>UpdateUsrData</command>
            <terminal>SAPext</terminal>
            <data>
                <object>{idcode}</object>
                {data_fields}
            </data>
        </msg>
        """
        headers = {"Content-Type": "application/xml"}
        success, response = await self.post(data=xml_payload, headers=headers)
        logging.info(f"[ XTRACK ] update_usrdata response: {response}")
        return success, response

    async def update_home_location(self, idcode: str, homelocation: str):
        xml_payload = f"""
        <msg>
            <command>UpdateHomeLocation</command>
            <terminal>SAPext</terminal>
            <data>
                <object>{idcode}</object>
                <homelocation>{homelocation}</homelocation>
            </data>
        </msg>
        """
        headers = {"Content-Type": "application/xml"}
        success, response = await self.post(data=xml_payload, headers=headers)
        logging.info(f"[ XTRACK ] update_home_location response: {response}")
        return success, response

    async def update_active(self, idcode: str, active: str):
        active_value = str(active).lower()
        xml_payload = f"""
        <msg>
            <command>UpdateActive</command>
            <terminal>SAPext</terminal>
            <data>
                <object>{idcode}</object>
                <active>{active_value}</active>
            </data>
        </msg>
        """
        headers = {"Content-Type": "application/xml"}
        success, response = await self.post(data=xml_payload, headers=headers)
        logging.info(f"[ XTRACK ] update_active response: {response}")
        return success, response

    async def update_due_date(self, idcode: str, duedate: str):
        xml_payload = f"""
        <msg>
            <command>UpdateDueDate</command>
            <terminal>SAPext</terminal>
            <data>
                <object>{idcode}</object>
                <duedate>{duedate}</duedate>
            </data>
        </msg>
        """
        headers = {"Content-Type": "application/xml"}
        success, response = await self.post(data=xml_payload, headers=headers)
        logging.info(f"[ XTRACK ] update_due_date response: {response}")
        return success, response

    async def update_last_seen(self, idcode: str, lastseen: str):
        xml_payload = f"""
        <msg>
            <command>UpdateLastSeen</command>
            <terminal>SAPext</terminal>
            <data>
                <object>{idcode}</object>
                <lastseen>{lastseen}</lastseen>
            </data>
        </msg>
        """
        headers = {"Content-Type": "application/xml"}
        success, response = await self.post(data=xml_payload, headers=headers)
        logging.info(f"[ XTRACK ] update_last_seen response: {response}")
        return success, response

    async def get_rep_hist_loc(self, startdate: str, enddate: str, object_id: str, column: str):
        xml_payload = f"""
        <msg>
            <command>GetRepHistLoc</command>
            <terminal>SAPext</terminal>
            <data>
                <startdate>{startdate}</startdate>
                <enddate>{enddate}</enddate>
                <object>{object_id}</object>
                <column>{column}</column>
            </data>
        </msg>
        """
        headers = {"Content-Type": "application/xml"}
        success, response = await self.post(data=xml_payload, headers=headers)
        xml_response = response.get("raw_response", None) if success else None
        results = []
        if success and xml_response:
            try:
                root = ET.fromstring(xml_response)
                for data_elem in root.findall(".//data"):
                    data_dict = {child.tag: child.text for child in data_elem}
                    results.append(data_dict)
                logging.info(f"[ XTRACK ] get_rep_hist_loc parsed data: {len(results)} items")
            except Exception as e:
                logging.error(f"[ XTRACK ] XML parsing error: {e}")
                return False, {"error": "XML parsing failed", "detail": str(e)}
        else:
            logging.info(f"[ XTRACK ] get_rep_hist_loc response: {xml_response}")
        return success, results if success else response
