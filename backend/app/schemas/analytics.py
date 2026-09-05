from typing import Optional
from pydantic import BaseModel, Field

class MonthlyTrendItem(BaseModel):
    month: str = Field(..., example="2018-01-01")
    total_orders: int
    total_items_sold: int
    product_revenue: float
    freight_revenue: float
    gross_revenue: float
    aov: float
    prev_month_revenue: Optional[float] = None
    mom_revenue_growth_pct: Optional[float] = None
    mom_order_growth_pct: Optional[float] = None
    mom_aov_growth_pct: Optional[float] = None

class CategoryItem(BaseModel):
    category: str = Field(..., example="health_beauty")
    total_orders: int
    units_sold: int
    total_revenue: float
    avg_item_price: float
    avg_review_score: Optional[float] = None
    revenue_share_percent: float

class StateItem(BaseModel):
    state: str = Field(..., example="SP")
    active_customers: int
    total_orders: int
    total_product_revenue: float
    total_freight_revenue: float
    total_gross_revenue: float
    avg_freight_cost: float
    revenue_share_percent: float

class SellerItem(BaseModel):
    seller_id: str
    seller_city: str
    seller_state: str
    total_orders_fulfilled: int
    units_sold: int
    unique_products_offered: int
    total_sales_revenue: float
    avg_seller_review_score: Optional[float] = None

class DeliverySLAItem(BaseModel):
    delivery_status: str = Field(..., example="On-Time")
    order_count: int
    percentage: float
    avg_actual_delivery_days: Optional[float] = None
    avg_estimated_delivery_days: Optional[float] = None
    avg_delay_days: Optional[float] = None

class PaymentItem(BaseModel):
    payment_type: str = Field(..., example="credit_card")
    order_count: int
    total_payment_value: float
    avg_payment_amount: float
    avg_installments: float
