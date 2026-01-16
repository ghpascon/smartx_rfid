import logging
import httpx


class WebhookXtrack:
    def __init__(self, url: str, timeout: int = 5):
        self.url = url
        self.timeout = timeout

    async def post(self, tag: dict):
        try:
            payload = f"""<msg>
                        <command>ReportRead</command>
                        <data>EVENT=|DEVICENAME={tag.get("device", "")}|ANTENNANAME={tag.get("ant", "")}|TAGID={tag.get("epc", "")}|</data>
                        <cmpl>STATE=|DATA1=|DATA2=|DATA3=|DATA4=|DATA5=|</cmpl>
                        </msg>"""
            async with httpx.AsyncClient() as client:
                await client.post(
                    self.url,
                    content=payload,
                    headers={"Content-Type": "application/xml"},
                    timeout=self.timeout,
                )
        except Exception as e:
            logging.info(f"Error Xtrack: {e}")
