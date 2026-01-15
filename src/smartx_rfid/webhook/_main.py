
import asyncio
import logging
from typing import Optional, Dict, Any

import httpx


class WebhookManager:
    def __init__(
            self,
            url: str,
            timeout: float = 5.0,
            max_retries: int = 2,
        ):
        self.url = url
        self.timeout = timeout  
        self.max_retries = max_retries

        self.default_headers = {
            "Content-Type": "application/json",
            "User-Agent": "SmartX-Connector/1.0"
        } 
        
    async def post(self, device: str, event_type: str, event_data: Any = None, headers: Optional[Dict[str, str]] = None) -> bool:
        """
        Sends data via POST to the configured webhook URL.
        
        Args:
            device: Name of the device sending the webhook
            event_type: Type of event being sent
            event_data: Data to be sent (will be converted to JSON)
            headers: Optional headers for the request
            
        Returns:
            bool: True if sent successfully, False otherwise
        """
        
        if not self.url:
            logging.warning("⚠️ WEBHOOK_URL not configured in settings")
            return False
        
        payload = {
            "device": device,
            "event_type": event_type,
            "event_data": event_data
        }
            
        
        
        # Merge with custom headers if provided
        if headers:
            self.default_headers.update(headers)
            
        retries = 0
        last_error = None
        
        while retries < self.max_retries:
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(
                        self.url,
                        json=payload,
                        headers=self.default_headers
                    )
                    
                    # Consider success if status 2xx
                    if response.status_code < 300:
                        logging.info(f"✅ Webhook sent successfully to {self.url} - Status: {response.status_code}")
                        return True
                    else:
                        logging.warning(f"⚠️ Webhook failed - Status: {response.status_code} - Response: {response.text[:200]}")
                        return False
                        
            except httpx.TimeoutException:
                last_error = f"Timeout after {self.timeout}s"
                retries += 1
                logging.warning(f"⏰ Webhook timeout (attempt {retries}/{self.max_retries})")
                
            except httpx.ConnectError:
                last_error = "Connection error"
                retries += 1
                logging.warning(f"🔌 Webhook connection error (attempt {retries}/{self.max_retries})")
                
            except Exception as e:
                last_error = str(e)
                retries += 1
                logging.error(f"❌ Webhook error (attempt {retries}/{self.max_retries}): {e}")
            
            # Wait before retrying (exponential backoff)
            if retries < self.max_retries:
                wait_time = 2 ** retries  # 2s, 4s, 8s...
                logging.info(f"🔁 Retrying webhook in {wait_time}s...")
                await asyncio.sleep(wait_time)
        
        # If we reached here, all attempts failed
        logging.error(f"❌ Webhook failed after {self.max_retries} attempts. Last error: {last_error}")
        return False

