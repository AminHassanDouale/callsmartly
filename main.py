from fastapi import FastAPI, Depends, HTTPException, Form, APIRouter
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
import models
import schemas
import crud
from database import engine, get_db
from dmoney_service import DMoneyService
from models import OrderStatus

# Create all database tables
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Multi-Merchant D-Money Payment Gateway", version="1.0.0")

# ==================== HOME PAGE ====================
@app.get("/", response_class=HTMLResponse)
def read_root():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>D-Money Payment Gateway</title>
        <style>
            body { font-family: Arial, sans-serif; max-width: 800px; margin: 50px auto; padding: 20px; }
            h1 { color: #333; }
            .endpoint { background: #f5f5f5; padding: 10px; margin: 10px 0; border-radius: 5px; }
            code { background: #e0e0e0; padding: 2px 5px; border-radius: 3px; }
            .section { margin: 30px 0; }
        </style>
    </head>
    <body>
        <h1>Multi-Merchant D-Money Payment Gateway</h1>
        <p>Each merchant gets unique API credentials to integrate with D-Money payment system.</p>
        
        <div class="section">
            <h2>Merchant Management:</h2>
            <div class="endpoint">
                <strong>POST /merchants/register</strong> - Register new merchant
            </div>
            <div class="endpoint">
                <strong>GET /merchants</strong> - List all merchants
            </div>
            <div class="endpoint">
                <strong>GET /merchants/{merchant_id}</strong> - Get merchant details
            </div>
        </div>
        
        <div class="section">
            <h2>Payment Operations:</h2>
            <div class="endpoint">
                <strong>POST /api/preorder</strong> - Create payment order
            </div>
            <div class="endpoint">
                <strong>POST /api/query-order</strong> - Query order status
            </div>
            <div class="endpoint">
                <strong>GET /api/orders/{merch_order_id}</strong> - Get order details
            </div>
            <div class="endpoint">
                <strong>POST /api/create-payment</strong> - Unified payment creation
            </div>
        </div>
        
        <div class="section">
            <h2>Testing Endpoints:</h2>
            <div class="endpoint">
                <strong>POST /test/full-payment-flow</strong> - Complete payment flow test
            </div>
            <div class="endpoint">
                <strong>POST /test/generate-checkout-url</strong> - Generate checkout URL
            </div>
            <div class="endpoint">
                <strong>POST /test/test-preorder</strong> - Test preorder creation
            </div>
            <div class="endpoint">
                <strong>POST /test/query-order</strong> - Test query order
            </div>
        </div>
        
        <div class="section">
            <h2>Documentation:</h2>
            <div class="endpoint">
                <strong>GET /docs</strong> - Swagger UI
            </div>
            <div class="endpoint">
                <strong>GET /api/merchant/{merchant_id}/api-docs</strong> - Merchant API Documentation
            </div>
        </div>
    </body>
    </html>
    """

# ==================== MERCHANT MANAGEMENT ====================

@app.post("/merchants/register", response_model=schemas.MerchantResponse)
async def register_merchant(
    name: str = Form(...),
    email: str = Form(...),
    dmoney_app_key: str = Form(...),
    dmoney_app_secret: str = Form(...),
    dmoney_app_id: str = Form(...),
    dmoney_merch_code: str = Form(...),
    notify_url: str = Form(...),
    redirect_url: str = Form(...),
    dmoney_private_key: str = Form(...),
    dmoney_public_key: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """Register a new merchant"""
    existing = crud.get_merchant_by_email(db, email)
    if existing:
        raise HTTPException(status_code=400, detail="Merchant with this email already exists")
    
    try:
        from cryptography.hazmat.primitives import serialization
        serialization.load_pem_private_key(
            dmoney_private_key.encode('utf-8'),
            password=None
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid private key format: {str(e)}")
    
    merchant_data = {
        "name": name,
        "email": email,
        "dmoney_app_key": dmoney_app_key,
        "dmoney_app_secret": dmoney_app_secret,
        "dmoney_app_id": dmoney_app_id,
        "dmoney_merch_code": dmoney_merch_code,
        "dmoney_private_key": dmoney_private_key,
        "dmoney_public_key": dmoney_public_key,
        "notify_url": notify_url,
        "redirect_url": redirect_url
    }
    
    merchant = crud.create_merchant(db, merchant_data)
    return merchant

@app.get("/merchants", response_model=List[schemas.MerchantResponse])
def list_merchants(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """List all active merchants"""
    merchants = crud.get_all_merchants(db, skip=skip, limit=limit)
    return merchants

@app.get("/merchants/{merchant_id}", response_model=schemas.MerchantResponse)
def get_merchant_details(merchant_id: int, db: Session = Depends(get_db)):
    """Get merchant details"""
    merchant = crud.get_merchant(db, merchant_id)
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")
    return merchant

# ==================== PAYMENT OPERATIONS ====================

@app.post("/api/preorder", response_model=schemas.PreorderResponse)
async def create_preorder(
    preorder_data: schemas.PreorderRequest,
    db: Session = Depends(get_db)
):
    """Create payment order"""
    try:
        merchant = crud.get_merchant(db, preorder_data.merchant_id)
        
        if not merchant:
            raise HTTPException(status_code=404, detail="Merchant not found")
        
        if not merchant.is_active:
            raise HTTPException(status_code=400, detail="Merchant is inactive")
        
        dmoney = DMoneyService(merchant)
        order = crud.create_order(db, preorder_data.dict())
        token = dmoney.get_valid_token(db)
        
        order_payload = {
            "merch_order_id": order.merch_order_id,
            "total_amount": order.total_amount,
            "currency": order.currency,
            "title": order.product_name,
            "timeout_express": preorder_data.timeout_express
        }
        
        payment_response = dmoney.create_preorder(token, order_payload)
        
        if payment_response.get("code") != "0" or payment_response.get("result") != "SUCCESS":
            raise HTTPException(
                status_code=400,
                detail=payment_response.get("msg", "Payment creation failed")
            )
        
        prepay_id = payment_response["biz_content"]["prepay_id"]
        checkout_url = dmoney.generate_checkout_url(prepay_id)
        
        crud.update_order_with_payment(
            db, order.merch_order_id, prepay_id, checkout_url, payment_response
        )
        
        return schemas.PreorderResponse(
            success=True,
            merch_order_id=order.merch_order_id,
            prepay_id=prepay_id,
            checkout_url=checkout_url,
            message="Preorder created successfully",
            order_id=order.id,
            merchant_name=merchant.name
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/query-order", response_model=schemas.QueryOrderResponse)
async def query_order(
    query_data: schemas.QueryOrderRequest,
    db: Session = Depends(get_db)
):
    """Query order status"""
    try:
        merchant = crud.get_merchant(db, query_data.merchant_id)
        
        if not merchant:
            raise HTTPException(status_code=404, detail="Merchant not found")
        
        dmoney = DMoneyService(merchant)
        token = dmoney.get_valid_token(db)
        query_response = dmoney.query_order(token, query_data.merch_order_id)
        
        if query_response.get("code") != "0" or query_response.get("result") != "SUCCESS":
            raise HTTPException(
                status_code=400,
                detail=query_response.get("msg", "Query order failed")
            )
        
        biz_content = query_response.get("biz_content", {})
        
        local_order = crud.get_order_by_merch_id(db, query_data.merch_order_id)
        if local_order and biz_content.get("order_status"):
            status_mapping = {
                "Paying": OrderStatus.PAYING,
                "Completed": OrderStatus.COMPLETED,
                "Failure": OrderStatus.FAILED,
                "Expired": OrderStatus.EXPIRED
            }
            new_status = status_mapping.get(biz_content.get("order_status"))
            if new_status:
                local_order.status = new_status
                local_order.payment_order_id = biz_content.get("payment_order_id")
                local_order.updated_at = datetime.utcnow()
                db.commit()
        
        return schemas.QueryOrderResponse(
            success=True,
            merch_order_id=biz_content.get("merch_order_id"),
            order_status=biz_content.get("order_status"),
            payment_order_id=biz_content.get("payment_order_id"),
            trans_time=biz_content.get("trans_time"),
            trans_currency=biz_content.get("trans_currency"),
            total_amount=biz_content.get("total_amount"),
            prepay_id=biz_content.get("prepay_id"),
            message="Order query successful",
            full_response=query_response
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/notify", response_model=schemas.NotifyResponse)
async def payment_notify(notify_data: schemas.NotifyRequest, db: Session = Depends(get_db)):
    """Webhook for payment notifications"""
    try:
        order = crud.update_order_status_from_notify(db, notify_data.dict())
        
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        
        return schemas.NotifyResponse(
            success=True,
            message=f"Payment notification processed. Status: {notify_data.trade_status}"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/orders/{merch_order_id}")
def get_order_status(merch_order_id: str, db: Session = Depends(get_db)):
    """Get order details"""
    order = crud.get_order_by_merch_id(db, merch_order_id)
    
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    return {
        "order_id": order.id,
        "merchant_id": order.merchant_id,
        "merchant_name": order.merchant.name,
        "merch_order_id": order.merch_order_id,
        "product_name": order.product_name,
        "total_amount": order.total_amount,
        "currency": order.currency,
        "status": order.status.value,
        "prepay_id": order.prepay_id,
        "checkout_url": order.checkout_url,
        "customer_name": order.customer_name,
        "created_at": order.created_at,
        "updated_at": order.updated_at
    }

@app.post("/api/create-payment")
async def create_payment(
    merchant_id: int = Form(...),
    product_name: str = Form(...),
    total_amount: float = Form(...),
    customer_name: str = Form(...),
    customer_email: str = Form(...),
    customer_phone: Optional[str] = Form(None),
    quantity: int = Form(1),
    currency: str = Form("DJF"),
    timeout_express: str = Form("120m"),
    db: Session = Depends(get_db)
):
    """
    Unified endpoint: Creates complete payment in one call
    Returns: order details + checkout URL ready to use
    """
    try:
        merchant = crud.get_merchant(db, merchant_id)
        if not merchant:
            raise HTTPException(status_code=404, detail="Merchant not found")
        
        if not merchant.is_active:
            raise HTTPException(status_code=400, detail="Merchant is inactive")
        
        dmoney = DMoneyService(merchant)
        token = dmoney.get_valid_token(db)
        merch_order_id = crud.generate_merch_order_id()
        
        order_data = {
            "merchant_id": merchant_id,
            "merch_order_id": merch_order_id,
            "product_name": product_name,
            "quantity": quantity,
            "total_amount": total_amount,
            "currency": currency,
            "customer_name": customer_name,
            "customer_email": customer_email,
            "customer_phone": customer_phone,
            "timeout_express": timeout_express
        }
        order = crud.create_order(db, order_data)
        
        order_payload = {
            "merch_order_id": merch_order_id,
            "total_amount": total_amount,
            "currency": currency,
            "title": product_name,
            "timeout_express": timeout_express
        }
        
        payment_response = dmoney.create_preorder(token, order_payload)
        
        if payment_response.get("code") != "0" or payment_response.get("result") != "SUCCESS":
            raise HTTPException(
                status_code=400,
                detail=payment_response.get("msg", "Payment creation failed")
            )
        
        prepay_id = payment_response["biz_content"]["prepay_id"]
        checkout_url = dmoney.generate_checkout_url(prepay_id)
        
        crud.update_order_with_payment(
            db, merch_order_id, prepay_id, checkout_url, payment_response
        )
        
        return {
            "success": True,
            "message": "Payment created successfully",
            "merchant": {
                "id": merchant.id,
                "name": merchant.name
            },
            "order": {
                "id": order.id,
                "merch_order_id": merch_order_id,
                "product_name": product_name,
                "total_amount": total_amount,
                "currency": currency,
                "customer_name": customer_name,
                "customer_email": customer_email,
                "status": order.status.value
            },
            "payment": {
                "prepay_id": prepay_id,
                "checkout_url": checkout_url,
                "expires_in": timeout_express
            },
            "created_at": order.created_at.strftime("%Y-%m-%d %H:%M:%S")
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==================== API DOCUMENTATION ENDPOINT ====================

@app.get("/api/merchant/{merchant_id}/api-docs")
async def get_merchant_api_documentation(merchant_id: int, db: Session = Depends(get_db)):
    """
    Generate API documentation for a specific merchant
    Shows them exactly how to integrate
    """
    merchant = crud.get_merchant(db, merchant_id)
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")
    
    base_url = "http://127.0.0.1:8001"
    
    return {
        "merchant_id": merchant.id,
        "merchant_name": merchant.name,
        "api_endpoint": f"{base_url}/api/create-payment",
        "method": "POST",
        "content_type": "application/x-www-form-urlencoded",
        "required_fields": {
            "merchant_id": merchant.id,
            "product_name": "Product name",
            "total_amount": "Amount in DJF",
            "customer_name": "Customer full name",
            "customer_email": "Customer email"
        },
        "optional_fields": {
            "customer_phone": "Customer phone number",
            "quantity": "Quantity (default: 1)",
            "currency": "Currency code (default: DJF)",
            "timeout_express": "Payment timeout (default: 120m)"
        },
        "example_curl": f"""curl -X POST {base_url}/api/create-payment \\
  -d "merchant_id={merchant.id}" \\
  -d "product_name=Test Product" \\
  -d "total_amount=1000" \\
  -d "customer_name=John Doe" \\
  -d "customer_email=john@example.com" \\
  -d "customer_phone=77123456" \\
  -d "quantity=1" \\
  -d "currency=DJF" \\
  -d "timeout_express=120m" """,
        "example_response": {
            "success": True,
            "message": "Payment created successfully",
            "order": {
                "merch_order_id": "ORD_20231006_ABC123",
                "product_name": "Test Product",
                "total_amount": 1000,
                "currency": "DJF"
            },
            "payment": {
                "checkout_url": "https://checkout-url-here",
                "prepay_id": "prepay_id_here",
                "expires_in": "120m"
            }
        }
    }

# ==================== TEST ENDPOINTS ====================

test_router = APIRouter(prefix="/test", tags=["Testing"])

@test_router.post("/full-payment-flow")
async def test_full_payment_flow(
    merchant_id: int,
    product_name: str = "Test Product",
    amount: float = 100.0,
    customer_name: str = "Test Customer",
    customer_email: str = "test@example.com",
    db: Session = Depends(get_db)
):
    """Complete payment flow: preorder + checkout URL generation"""
    merchant = crud.get_merchant(db, merchant_id)
    
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")
    
    dmoney = DMoneyService(merchant)
    
    try:
        token = dmoney.get_valid_token(db)
        order_id = crud.generate_merch_order_id()
        
        order_payload = {
            "merch_order_id": order_id,
            "total_amount": amount,
            "currency": "DJF",
            "title": product_name,
            "timeout_express": "120m"
        }
        
        payment_response = dmoney.create_preorder(token, order_payload)
        
        if payment_response.get("code") != "0" or payment_response.get("result") != "SUCCESS":
            return {
                "success": False,
                "error": payment_response.get("msg", "Preorder failed"),
                "full_response": payment_response
            }
        
        prepay_id = payment_response["biz_content"]["prepay_id"]
        checkout_url = dmoney.generate_checkout_url(prepay_id)
        
        return {
            "success": True,
            "merchant_id": merchant.id,
            "merchant_name": merchant.name,
            "order_details": {
                "merch_order_id": order_id,
                "product_name": product_name,
                "amount": amount,
                "currency": "DJF"
            },
            "payment_details": {
                "prepay_id": prepay_id,
                "checkout_url": checkout_url,
                "timeout": "120 minutes"
            },
            "next_steps": "Open checkout_url in browser to complete payment",
            "message": "Full payment flow completed successfully!"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@test_router.post("/get-token")
async def test_get_token(merchant_id: int, db: Session = Depends(get_db)):
    """Test token generation"""
    merchant = crud.get_merchant(db, merchant_id)
    
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")
    
    dmoney = DMoneyService(merchant)
    
    try:
        token, expires_at = dmoney.generate_token()
        
        return {
            "success": True,
            "token": token,
            "expires_at": expires_at.strftime("%Y-%m-%d %H:%M:%S"),
            "merchant_id": merchant.id,
            "merchant_name": merchant.name
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Register test router
app.include_router(test_router)

# ==================== MAIN ====================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)