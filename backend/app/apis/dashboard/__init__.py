from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Optional
import databutton as db
import json
from datetime import datetime, timedelta
import random

router = APIRouter()

class AIStatus(BaseModel):
    store_level: bool
    product_level: bool
    user_level: bool

class RecentInteraction(BaseModel):
    id: str
    user_id: str
    user_name: str
    message: str
    timestamp: str
    is_ai_response: bool

class RecentSale(BaseModel):
    id: str
    product_name: str
    amount: float
    customer_name: str
    timestamp: str

class DashboardStats(BaseModel):
    total_products: int
    total_templates: int
    total_deliveries: int
    recent_sales: List[RecentSale]
    recent_interactions: List[RecentInteraction]
    ai_status: AIStatus
    sales_by_day: Dict[str, float]
    interactions_by_day: Dict[str, int]

# In a real app, this would fetch from a database
def get_ai_status_from_storage() -> AIStatus:
    # For now, we'll use mock data
    try:
        data = db.storage.json.get("ai_status", default=None)
        if data:
            return AIStatus(**data)
    except:
        pass
    
    # Default values if no data exists
    return AIStatus(
        store_level=False,
        product_level=False,
        user_level=False
    )

def save_ai_status_to_storage(status: AIStatus):
    db.storage.json.put("ai_status", status.dict())

@router.get("/dashboard/stats")
def get_dashboard_stats() -> DashboardStats:
    """Get dashboard statistics"""
    # Get AI status
    ai_status = get_ai_status_from_storage()
    
    # In a real app, these would be fetched from a database
    # For now, we'll use mock data that looks realistic
    
    # Generate dates for the last 7 days
    today = datetime.now()
    dates = [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]
    dates.reverse()  # So they're in chronological order
    
    # Generate mock sales and interactions data by day
    sales_by_day = {date: round(random.uniform(50, 500), 2) for date in dates}
    interactions_by_day = {date: random.randint(5, 30) for date in dates}
    
    # Generate mock recent sales
    recent_sales = [
        RecentSale(
            id=f"sale-{i}",
            product_name=f"Digital Product {i}",
            amount=round(random.uniform(10, 100), 2),
            customer_name=f"Customer {i}",
            timestamp=(today - timedelta(hours=random.randint(1, 24))).isoformat()
        ) for i in range(1, 6)  # 5 recent sales
    ]
    
    # Generate mock recent interactions
    recent_interactions = [
        RecentInteraction(
            id=f"interaction-{i}",
            user_id=f"user-{i}",
            user_name=f"User {i}",
            message="How do I download my product?" if i % 2 == 0 else "Thank you for your purchase!",
            timestamp=(today - timedelta(hours=random.randint(1, 12))).isoformat(),
            is_ai_response=i % 3 == 0  # Every third message is from AI
        ) for i in range(1, 6)  # 5 recent interactions
    ]
    
    return DashboardStats(
        total_products=random.randint(5, 15),
        total_templates=random.randint(3, 8),
        total_deliveries=random.randint(20, 50),
        recent_sales=recent_sales,
        recent_interactions=recent_interactions,
        ai_status=ai_status,
        sales_by_day=sales_by_day,
        interactions_by_day=interactions_by_day
    )

@router.put("/dashboard/ai-status")
def update_ai_status(status: AIStatus) -> AIStatus:
    """Update AI status"""
    save_ai_status_to_storage(status)
    return status
