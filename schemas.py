from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional

class MerchantCreate(BaseModel):
    name: str
    email: EmailStr
    dmoney_app_key: str
    dmoney_app_secret: str
    dmoney_app_id: str
    dmoney_merch_code: str
    dmoney_private_key: str
    dmoney_public_key: Optional[str] = None
    notify_url: str
    redirect_url: str

class MerchantResponse(BaseModel):
    id: int
    name: str
    email: str
    dmoney_app_id: str
    dmoney_merch_code: str
    notify_url: str
    redirect_url: str
    is_active: bool
    created_at: datetime
    
    class Config:
        from_attributes = True

class PreorderRequest(BaseModel):
    merchant_id: int
    product_name: str
    quantity: int
    total_amount: float
    currency: str = "DJF"
    customer_name: str
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    timeout_express: Optional[str] = "120m"

class PreorderResponse(BaseModel):
    success: bool
    merch_order_id: str
    prepay_id: Optional[str] = None
    checkout_url: Optional[str] = None
    message: str
    order_id: int
    merchant_name: str
    
class NotifyRequest(BaseModel):
    appid: str
    merch_code: str
    merch_order_id: str
    notify_time: str
    notify_url: str
    payment_order_id: str
    total_amount: str
    trans_currency: str
    trade_status: str
    trans_end_time: str
    callback_info: Optional[str] = None
    sign: str
    sign_type: str

class NotifyResponse(BaseModel):
    success: bool
    message: str

class QueryOrderRequest(BaseModel):
    merchant_id: int
    merch_order_id: str

class QueryOrderResponse(BaseModel):
    success: bool
    merch_order_id: str
    order_status: Optional[str] = None
    payment_order_id: Optional[str] = None
    trans_time: Optional[str] = None
    trans_currency: Optional[str] = None
    total_amount: Optional[str] = None
    prepay_id: Optional[str] = None
    message: str
    full_response: Optional[dict] = None