from sqlalchemy import Column, Integer, String, Float, DateTime, Text, Boolean, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base
import enum

class OrderStatus(enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    PAYING = "Paying"
    COMPLETED = "Completed"
    FAILED = "Failure"
    EXPIRED = "Expired"

class Merchant(Base):
    __tablename__ = "merchants"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    
    # D-Money API Credentials
    dmoney_app_key = Column(String(255), nullable=False)
    dmoney_app_secret = Column(String(255), nullable=False)
    dmoney_app_id = Column(String(255), nullable=False)
    dmoney_merch_code = Column(String(50), nullable=False)
    
    # RSA Keys
    dmoney_private_key = Column(Text, nullable=False)
    dmoney_public_key = Column(Text, nullable=True)
    
    # Callback URLs
    notify_url = Column(String(500), nullable=False)
    redirect_url = Column(String(500), nullable=False)
    
    # Token caching
    cached_token = Column(String(1000), nullable=True)
    token_expires_at = Column(DateTime, nullable=True)
    
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    orders = relationship("Order", back_populates="merchant")

class Order(Base):
    __tablename__ = "orders"
    
    id = Column(Integer, primary_key=True, index=True)
    merchant_id = Column(Integer, ForeignKey("merchants.id"), nullable=False)
    merch_order_id = Column(String(100), unique=True, index=True, nullable=False)
    
    product_name = Column(String(255), nullable=False)
    quantity = Column(Integer, nullable=False)
    total_amount = Column(Float, nullable=False)
    currency = Column(String(10), default="DJF")
    status = Column(SQLEnum(OrderStatus), default=OrderStatus.PENDING)
    
    # D-Money fields
    prepay_id = Column(String(255), nullable=True)
    payment_order_id = Column(String(255), nullable=True)
    checkout_url = Column(String(1000), nullable=True)
    
    # Customer info
    customer_name = Column(String(255), nullable=False)
    customer_email = Column(String(255), nullable=False)
    customer_phone = Column(String(50), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    trans_end_time = Column(DateTime, nullable=True)
    
    callback_info = Column(Text, nullable=True)
    gateway_response = Column(Text, nullable=True)
    
    merchant = relationship("Merchant", back_populates="orders") 