from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.database import get_db
from backend.models import Category, TrendingItem
from backend.schemas import CategoryListResponse, CategoryResponse

router = APIRouter(prefix="/api/v1/categories", tags=["categories"])

@router.get("", response_model=CategoryListResponse)
def list_categories(db: Session = Depends(get_db)):
    """Retrieve all categories along with the count of active trending items assigned to each."""
    categories = db.query(Category).order_by(Category.name.asc()).all()

    # Query counts per category
    counts_raw = db.query(
        TrendingItem.category_id,
        func.count(TrendingItem.id)
    ).group_by(TrendingItem.category_id).all()

    counts_dict = {cat_id: cnt for cat_id, cnt in counts_raw if cat_id is not None}

    cat_responses = []
    for cat in categories:
        cat_responses.append(CategoryResponse(
            id=cat.id,
            name=cat.name,
            color=cat.color,
            item_count=counts_dict.get(cat.id, 0)
        ))

    return CategoryListResponse(
        total_categories=len(cat_responses),
        categories=cat_responses
    )
