from typing import Optional

import httpx
from fastapi import Depends, FastAPI, HTTPException, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import schemas
from .config import settings
from .database import Base, engine, get_db
from .dependencies import CurrentUser, get_current_user
from .models import Cart, CartItem, WishlistItem, utcnow

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Cart and Wishlist Service")

MAX_QTY = 10
TIMEOUT = httpx.Timeout(3.0)


# ---------- talking to other services ----------

def fetch_product(product_id: int) -> dict:
    try:
        response = httpx.get(
            f"{settings.PRODUCT_SERVICE_URL}/products/{product_id}", timeout=TIMEOUT
        )
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Product service is not available right now")
    if response.status_code == 404:
        raise HTTPException(status_code=404, detail="Product not found")
    if response.status_code != 200:
        raise HTTPException(status_code=502, detail="Product service returned an error")
    return response.json()


def fetch_available(product_id: int) -> int:
    try:
        response = httpx.get(
            f"{settings.INVENTORY_SERVICE_URL}/inventory/{product_id}",
            headers={"X-Internal-Key": settings.INTERNAL_API_KEY},
            timeout=TIMEOUT,
        )
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Inventory service is not available right now")
    if response.status_code == 404:
        return 0  # no stock record means nothing to sell
    if response.status_code != 200:
        raise HTTPException(status_code=502, detail="Inventory service returned an error")
    return response.json()["quantity_available"]


# ---------- helper functions ----------

def get_cart(db: Session, user_id: int) -> Optional[Cart]:
    return db.query(Cart).filter(Cart.user_id == user_id).first()


def get_or_create_cart(db: Session, user_id: int) -> Cart:
    cart = get_cart(db, user_id)
    if cart is None:
        cart = Cart(user_id=user_id)
        db.add(cart)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            cart = get_cart(db, user_id)
        else:
            db.refresh(cart)
    return cart


def stock_message(available: int) -> str:
    if available <= 0:
        return "This product is out of stock"
    return f"Only {available} left in stock"


def build_view(cart: Optional[Cart]) -> schemas.CartOut:
    lines = []
    if cart is not None:
        for item in cart.items:
            name, price = item.product_name, item.unit_price
            available, issue = None, None
            try:
                product = fetch_product(item.product_id)
                name, price = product["name"], product["price"]
                available = fetch_available(item.product_id)
                if available < item.quantity:
                    issue = stock_message(available)
            except HTTPException as exc:
                if exc.status_code == 404:
                    issue = "This product is no longer available"
                else:
                    issue = "Could not check the latest price and stock"
            lines.append(
                schemas.CartItemOut(
                    item_id=item.id,
                    product_id=item.product_id,
                    name=name,
                    unit_price=price,
                    price_changed=price != item.unit_price,
                    quantity=item.quantity,
                    line_total=round(price * item.quantity, 2),
                    available_quantity=available,
                    issue=issue,
                )
            )
    return schemas.CartOut(
        items=lines,
        item_count=sum(l.quantity for l in lines),
        subtotal=round(sum(l.line_total for l in lines), 2),
        has_issues=any(l.issue for l in lines),
    )


def find_item(db: Session, user_id: int, item_id: int) -> CartItem:
    # Only items inside THIS user's cart can be found
    item = (
        db.query(CartItem)
        .join(Cart, Cart.id == CartItem.cart_id)
        .filter(CartItem.id == item_id, Cart.user_id == user_id)
        .first()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Cart item not found")
    return item


# ---------- cart APIs ----------

@app.get("/health")
def health():
    return {"status": "ok", "service": "cart"}


@app.get("/cart", response_model=schemas.CartOut)
def read_cart(
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    return build_view(get_cart(db, user.id))


@app.post("/cart/items", response_model=schemas.CartOut, status_code=201)
def add_item(
    data: schemas.CartItemAdd,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    product = fetch_product(data.product_id)
    available = fetch_available(data.product_id)
    cart = get_or_create_cart(db, user.id)

    item = next((i for i in cart.items if i.product_id == data.product_id), None)
    new_quantity = (item.quantity if item else 0) + data.quantity
    if new_quantity > MAX_QTY:
        raise HTTPException(
            status_code=400, detail=f"You can buy at most {MAX_QTY} of one product"
        )
    if available < new_quantity:
        raise HTTPException(status_code=409, detail=stock_message(available))

    if item:
        item.quantity = new_quantity
        item.unit_price = product["price"]
        item.product_name = product["name"]
    else:
        db.add(
            CartItem(
                cart_id=cart.id,
                product_id=data.product_id,
                product_name=product["name"],
                unit_price=product["price"],
                quantity=data.quantity,
            )
        )
    cart.updated_at = utcnow()
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Please try again")
    db.refresh(cart)
    return build_view(cart)


@app.patch("/cart/items/{item_id}", response_model=schemas.CartOut)
def update_item(
    item_id: int,
    data: schemas.CartItemUpdate,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    item = find_item(db, user.id, item_id)
    available = fetch_available(item.product_id)
    if available < data.quantity:
        raise HTTPException(status_code=409, detail=stock_message(available))
    item.quantity = data.quantity
    db.commit()
    cart = get_cart(db, user.id)
    return build_view(cart)


@app.delete("/cart/items/{item_id}", status_code=204)
def remove_item(
    item_id: int,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    item = find_item(db, user.id, item_id)
    db.delete(item)
    db.commit()
    return Response(status_code=204)


@app.delete("/cart", status_code=204)
def clear_cart(
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    cart = get_cart(db, user.id)
    if cart:
        for item in list(cart.items):
            db.delete(item)
        db.commit()
    return Response(status_code=204)


@app.post("/cart/validate", response_model=schemas.CartValidation)
def validate_cart(
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    view = build_view(get_cart(db, user.id))
    if not view.items:
        return schemas.CartValidation(valid=False, message="Your cart is empty", cart=view)
    if view.has_issues:
        return schemas.CartValidation(
            valid=False,
            message="Some items in your cart have problems. Please fix them before checkout.",
            cart=view,
        )
    return schemas.CartValidation(valid=True, message="Your cart is ready for checkout", cart=view)


# ---------- wishlist APIs ----------

@app.get("/wishlist", response_model=list[schemas.WishlistItemOut])
def read_wishlist(
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    rows = (
        db.query(WishlistItem)
        .filter(WishlistItem.user_id == user.id)
        .order_by(WishlistItem.id.desc())
        .all()
    )
    return [
        schemas.WishlistItemOut(
            item_id=r.id,
            product_id=r.product_id,
            product_name=r.product_name,
            added_at=r.created_at,
        )
        for r in rows
    ]


@app.post("/wishlist/items", response_model=schemas.WishlistItemOut, status_code=201)
def add_wishlist_item(
    data: schemas.WishlistAdd,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    product = fetch_product(data.product_id)
    exists = (
        db.query(WishlistItem.id)
        .filter(WishlistItem.user_id == user.id, WishlistItem.product_id == data.product_id)
        .first()
    )
    if exists:
        raise HTTPException(status_code=409, detail="This product is already in your wishlist")
    row = WishlistItem(
        user_id=user.id, product_id=data.product_id, product_name=product["name"]
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="This product is already in your wishlist")
    db.refresh(row)
    return schemas.WishlistItemOut(
        item_id=row.id,
        product_id=row.product_id,
        product_name=row.product_name,
        added_at=row.created_at,
    )


@app.delete("/wishlist/items/{item_id}", status_code=204)
def remove_wishlist_item(
    item_id: int,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    row = (
        db.query(WishlistItem)
        .filter(WishlistItem.id == item_id, WishlistItem.user_id == user.id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Wishlist item not found")
    db.delete(row)
    db.commit()
    return Response(status_code=204)