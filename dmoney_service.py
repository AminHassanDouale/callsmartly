import os
import time
import base64
import warnings
import requests
from typing import Dict, Any
from urllib3.exceptions import InsecureRequestWarning
from datetime import datetime, timedelta
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from dotenv import load_dotenv
from models import Merchant

# Supprimer les warnings SSL pour l'environnement de test
warnings.filterwarnings('ignore', category=InsecureRequestWarning)

load_dotenv()

class DMoneyService:
    def __init__(self, merchant: Merchant):
        self.merchant = merchant
        self.base_url = os.getenv("DMONEY_BASE_URL")
        self.checkout_base_url = os.getenv("DMONEY_CHECKOUT_BASE_URL")
        
    def get_valid_token(self, db) -> str:
        """Always generate fresh token on each request"""
        token, expires_at = self.generate_token()
        
        from crud import update_merchant_token
        update_merchant_token(db, self.merchant.id, token, expires_at)
        
        return token
    
    def generate_token(self) -> tuple[str, datetime]:
        """Step 1: Generate authentication token"""
        url = f"{self.base_url}/payment/v1/token"
        
        headers = {
            "X-APP-Key": self.merchant.dmoney_app_key,
            "Content-Type": "application/json"
        }
        
        payload = {
            "appSecret": self.merchant.dmoney_app_secret
        }
        
        response = requests.post(url, json=payload, headers=headers, verify=False)
        
        if response.status_code != 200:
            raise Exception(f"Token generation failed: {response.text}")
        
        data = response.json()
        token = data.get("token", "")
        
        if token.startswith("Bearer "):
            token = token[7:]
        
        expiration_str = data.get("expirationDate")
        expires_at = datetime.strptime(expiration_str, "%Y%m%d%H%M%S")
        
        return token, expires_at
    
    def _sign_request(self, params: Dict[str, Any]) -> str:
        """Generate RSA-PSS signature"""
        excluded = {'sign', 'sign_type', 'biz_content'}
        filtered_params = {
            k: str(v) for k, v in params.items() 
            if k not in excluded and v is not None and str(v).strip() != ''
        }
        
        sorted_items = sorted(filtered_params.items())
        raw_request = '&'.join(f"{k}={v}" for k, v in sorted_items)
        
        private_key = serialization.load_pem_private_key(
            self.merchant.dmoney_private_key.encode('utf-8'),
            password=None
        )
        
        signature = private_key.sign(
            raw_request.encode('utf-8'),
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=32
            ),
            hashes.SHA256()
        )
        
        return base64.b64encode(signature).decode('utf-8')
    
    def create_preorder(self, token: str, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """Step 2: Create preorder"""
        import secrets
        nonce_str = secrets.token_hex(16)
        timestamp = str(int(time.time()))
        
        # IMPORTANT: Convertir merch_code en string
        merch_code = str(self.merchant.dmoney_merch_code)
        
        sign_params = {
            "appid": self.merchant.dmoney_app_id,
            "business_type": "OnlineMerchant",
            "merch_code": merch_code,
            "merch_order_id": order_data["merch_order_id"],
            "method": "payment.preorder",
            "nonce_str": nonce_str,
            "notify_url": self.merchant.notify_url,
            "redirect_url": self.merchant.redirect_url,
            "timeout_express": order_data.get("timeout_express", "120m"),
            "timestamp": timestamp,
            "title": order_data["title"],
            "total_amount": str(order_data["total_amount"]),
            "trade_type": "Checkout",
            "trans_currency": order_data.get("currency", "DJF"),
            "version": "1.0"
        }
        
        signature = self._sign_request(sign_params)
        
        payload = {
            "nonce_str": nonce_str,
            "biz_content": {
                "trans_currency": order_data.get("currency", "DJF"),
                "total_amount": str(order_data["total_amount"]),
                "merch_order_id": order_data["merch_order_id"],
                "appid": self.merchant.dmoney_app_id,
                "merch_code": merch_code,
                "timeout_express": order_data.get("timeout_express", "120m"),
                "trade_type": "Checkout",
                "notify_url": self.merchant.notify_url,
                "redirect_url": self.merchant.redirect_url,
                "title": order_data["title"],
                "business_type": "OnlineMerchant"
            },
            "method": "payment.preorder",
            "version": "1.0",
            "sign_type": "SHA256WithRSA",
            "timestamp": timestamp,
            "sign": signature
        }
        
        url = f"{self.base_url}/payment/v1/merchant/preOrder"
        
        headers = {
            "Content-Type": "application/json",
            "X-APP-Key": self.merchant.dmoney_app_key,
            "Authorization": f"Bearer {token}"
        }
        
        response = requests.post(url, json=payload, headers=headers, verify=False)
        
        if response.status_code != 200:
            raise Exception(f"Preorder failed: {response.text}")
        
        return response.json()
    
    def generate_checkout_url(self, prepay_id: str) -> str:
        """Step 3: Generate checkout URL"""
        import secrets
        nonce_str = secrets.token_hex(16)
        timestamp = str(int(time.time()))
        
        # CRITICAL FIX: Convertir merch_code en string
        merch_code = str(self.merchant.dmoney_merch_code)
        appid = str(self.merchant.dmoney_app_id)
        
        params = {
            "appid": appid,
            "merch_code": merch_code,
            "nonce_str": nonce_str,
            "prepay_id": prepay_id,
            "timestamp": timestamp
        }
        
        signature = self._sign_request(params)
        
        # Debug: afficher les paramètres
        print(f"DEBUG - appid: {appid} (type: {type(appid).__name__})")
        print(f"DEBUG - merch_code: {merch_code} (type: {type(merch_code).__name__})")
        print(f"DEBUG - prepay_id: {prepay_id}")
        
        # Construire l'URL avec les valeurs en string - SANS encoder les paramètres de base
        from urllib.parse import quote
        checkout_url = (
            f"{self.checkout_base_url}/payment/web/paygate?"
            f"appid={appid}&"
            f"merch_code={merch_code}&"
            f"nonce_str={nonce_str}&"
            f"prepay_id={prepay_id}&"
            f"timestamp={timestamp}&"
            f"sign={quote(signature, safe='')}&"
            f"sign_type=SHA256WithRSA&"
            f"version=1.0&"
            f"trade_type=Checkout&"
            f"language=en"
        )
        
        print(f"DEBUG - Checkout URL: {checkout_url[:200]}...")
        
        return checkout_url
    
    def query_order(self, token: str, merch_order_id: str) -> Dict[str, Any]:
        """Query order status from D-Money"""
        import secrets
        nonce_str = secrets.token_hex(16)
        timestamp = str(int(time.time()))
        
        # IMPORTANT: Convertir merch_code en string
        merch_code = str(self.merchant.dmoney_merch_code)
        
        sign_params = {
            "appid": self.merchant.dmoney_app_id,
            "merch_code": merch_code,
            "merch_order_id": merch_order_id,
            "method": "payment.queryorder",
            "nonce_str": nonce_str,
            "timestamp": timestamp,
            "version": "1.0"
        }
        
        signature = self._sign_request(sign_params)
        
        payload = {
            "timestamp": timestamp,
            "method": "payment.queryorder",
            "nonce_str": nonce_str,
            "version": "1.0",
            "sign_type": "SHA256WithRSA",
            "sign": signature,
            "biz_content": {
                "appid": self.merchant.dmoney_app_id,
                "merch_code": merch_code,
                "merch_order_id": merch_order_id
            }
        }
        
        url = f"{self.base_url}/payment/v1/merchant/queryOrder"
        
        headers = {
            "Content-Type": "application/json",
            "X-APP-Key": self.merchant.dmoney_app_key,
            "Authorization": f"Bearer {token}"
        }
        
        response = requests.post(url, json=payload, headers=headers, verify=False)
        
        if response.status_code != 200:
            raise Exception(f"Query order failed: {response.text}")
        
        return response.json()