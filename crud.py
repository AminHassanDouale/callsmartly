from sqlalchemy.orm import Session
from datetime import datetime
import secrets
import json
from models import Merchant, Order, OrderStatus

# ==================== MERCHANT CRUD ====================

def get_merchant(db: Session, merchant_id: int):
    """Get merchant by ID"""
    return db.query(Merchant).filter(Merchant.id == merchant_id).first()

def get_merchant_by_email(db: Session, email: str):
    """Get merchant by email"""
    return db.query(Merchant).filter(Merchant.email == email).first()

def get_all_merchants(db: Session, skip: int = 0, limit: int = 100):
    """Get all active merchants"""
    return db.query(Merchant).filter(Merchant.is_active == True).offset(skip).limit(limit).all()

def create_merchant(db: Session, merchant_data: dict):
    """Create new merchant"""
    merchant = Merchant(
        name=merchant_data["name"],
        email=merchant_data["email"],
        dmoney_app_key=merchant_data["dmoney_app_key"],
        dmoney_app_secret=merchant_data["dmoney_app_secret"],
        dmoney_app_id=merchant_data["dmoney_app_id"],
        dmoney_merch_code=merchant_data["dmoney_merch_code"],
        dmoney_private_key=merchant_data["dmoney_private_key"],
        dmoney_public_key=merchant_data.get("dmoney_public_key"),
        notify_url=merchant_data["notify_url"],
        redirect_url=merchant_data["redirect_url"]
    )
    db.add(merchant)
    db.commit()
    db.refresh(merchant)
    return merchant

def update_merchant_token(db: Session, merchant_id: int, token: str, expires_at: datetime):
    """Update merchant's cached token"""
    merchant = get_merchant(db, merchant_id)
    if merchant:
        merchant.cached_token = token
        merchant.token_expires_at = expires_at
        merchant.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(merchant)
    return merchant

# ==================== ORDER CRUD ====================

def generate_merch_order_id() -> str:
    """Generate unique merchant order ID (alphanumeric only)"""
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    random_part = secrets.token_hex(4).upper()
    return f"ORD{timestamp}{random_part}"

def create_order(db: Session, order_data: dict):
    """Create new order"""
    merch_order_id = generate_merch_order_id()
    
    order = Order(
        merchant_id=order_data["merchant_id"],
        merch_order_id=merch_order_id,
        product_name=order_data["product_name"],
        quantity=order_data["quantity"],
        total_amount=order_data["total_amount"],
        currency=order_data.get("currency", "DJF"),
        customer_name=order_data["customer_name"],
        customer_email=order_data["customer_email"],
        customer_phone=order_data.get("customer_phone"),
        status=OrderStatus.PENDING
    )
    
    db.add(order)
    db.commit()
    db.refresh(order)
    return order

def get_order_by_merch_id(db: Session, merch_order_id: str):
    """Get order by merchant order ID"""
    return db.query(Order).filter(Order.merch_order_id == merch_order_id).first()

def update_order_with_payment(db: Session, merch_order_id: str, prepay_id: str, checkout_url: str, gateway_response: dict):
    """Update order with payment information"""
    order = get_order_by_merch_id(db, merch_order_id)
    if order:
        order.prepay_id = prepay_id
        order.checkout_url = checkout_url
        order.gateway_response = json.dumps(gateway_response)
        order.status = OrderStatus.PROCESSING
        order.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(order)
    return order

def update_order_status_from_notify(db: Session, notify_data: dict):
    """Update order status from payment notification"""
    order = get_order_by_merch_id(db, notify_data["merch_order_id"])
    
    if not order:
        return None
    
    status_mapping = {
        "Paying": OrderStatus.PAYING,
        "Completed": OrderStatus.COMPLETED,
        "Failure": OrderStatus.FAILED,
        "Expired": OrderStatus.EXPIRED
    }
    
    trade_status = notify_data.get("trade_status")
    order.status = status_mapping.get(trade_status, OrderStatus.PROCESSING)
    order.payment_order_id = notify_data.get("payment_order_id")
    order.callback_info = json.dumps(notify_data)
    
    if notify_data.get("trans_end_time"):
        try:
            order.trans_end_time = datetime.strptime(
                notify_data["trans_end_time"], 
                "%Y%m%d%H%M%S"
            )
        except:
            pass
    
    order.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(order)
    return order