from pydantic import BaseModel, Field

class KPISummaryResponse(BaseModel):
    product_revenue: float = Field(..., example=13221498.11, description="Total net product revenue in BRL (R$)")
    freight_revenue: float = Field(..., example=2198275.64, description="Total freight charges in BRL (R$)")
    gross_revenue: float = Field(..., example=15419773.75, description="Gross total revenue including product + freight")
    delivered_orders: int = Field(..., example=96478, description="Count of successfully delivered orders")
    active_customers: int = Field(..., example=93358, description="Count of unique customers")
    units_sold: int = Field(..., example=110197, description="Total line-item units sold")
    aov: float = Field(..., example=159.83, description="Average Order Value in BRL (R$)")
    csat: float = Field(..., example=4.16, description="Average Customer Satisfaction Score (1.0 to 5.0)")
