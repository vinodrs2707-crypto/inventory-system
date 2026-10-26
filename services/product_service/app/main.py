import csv
import io
import json
from typing import List, Literal, Optional

from fastapi import (
    Depends,
    FastAPI,
    File,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from pydantic import ValidationError
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, contains_eager

from . import schemas
from .database import Base, engine, get_db
from .dependencies import (
    CurrentUser,
    get_current_user,
    get_optional_user,
    require_roles,
)
from .models import Category, Product, RecentlyViewed, utcnow

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Product Catalog Service")

ADMIN = "administrator"
MAX_IMPORT_BYTES = 1_000_000
MAX_IMPORT_ROWS = 1000
REQUIRED_COLUMNS = {"name", "description", "category", "brand", "price"}


# ---------- helper functions ----------

def to_out(p: Product) -> schemas.ProductOut:
    return schemas.ProductOut(
        id=p.id,
        name=p.name,
        description=p.description,
        category=p.category.name,
        brand=p.brand,
        price=p.price,
        image_url=p.image_url,
        specifications=json.loads(p.specifications or "{}"),
        rating_average=p.rating_average,
        rating_count=p.rating_count,
        stock_quantity=p.stock_quantity,
        in_stock=p.stock_quantity > 0,
        created_at=p.created_at,
    )


def get_or_create_category(db: Session, name: str) -> Category:
    name = name.strip()
    category = db.query(Category).filter(func.lower(Category.name) == name.lower()).first()
    if category is None:
        category = Category(name=name)
        db.add(category)
        db.flush()
    return category


def product_exists(db: Session, name: str, brand: str) -> bool:
    return (
        db.query(Product.id)
        .filter(
            func.lower(Product.name) == name.strip().lower(),
            func.lower(Product.brand) == brand.strip().lower(),
            Product.is_active == True,  # noqa: E712
        )
        .first()
        is not None
    )


def get_active_product(db: Session, product_id: int) -> Product:
    product = (
        db.query(Product)
        .filter(Product.id == product_id, Product.is_active == True)  # noqa: E712
        .first()
    )
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


def parse_specs(text: str) -> dict:
    # CSV format: Color:Black;Battery:AA
    specs = {}
    for part in text.split(";"):
        if ":" in part:
            key, value = part.split(":", 1)
            if key.strip():
                specs[key.strip()] = value.strip()
    return specs


# ---------- APIs ----------

@app.get("/health")
def health():
    return {"status": "ok", "service": "product"}


@app.get("/categories", response_model=List[str])
def list_categories(db: Session = Depends(get_db)):
    return [c.name for c in db.query(Category).order_by(Category.name).all()]


@app.post("/products", response_model=schemas.ProductOut, status_code=201)
def create_product(
    data: schemas.ProductCreate,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_roles(ADMIN)),
):
    if product_exists(db, data.name, data.brand):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A product with this name and brand already exists",
        )
    category = get_or_create_category(db, data.category)
    product = Product(
        name=data.name.strip(),
        description=data.description.strip(),
        category_id=category.id,
        brand=data.brand.strip(),
        price=data.price,
        image_url=data.image_url,
        specifications=json.dumps(data.specifications),
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    return to_out(product)


@app.get("/products", response_model=schemas.ProductPage)
def list_products(
    search: Optional[str] = Query(None, max_length=100),
    category: Optional[str] = None,
    brand: Optional[str] = None,
    min_price: Optional[float] = Query(None, ge=0),
    max_price: Optional[float] = Query(None, ge=0),
    min_rating: Optional[float] = Query(None, ge=0, le=5),
    in_stock: Optional[bool] = None,
    sort_by: Literal["newest", "price", "name", "rating"] = "newest",
    order: Literal["asc", "desc"] = "desc",
    page: int = Query(1, ge=1),
    page_size: int = Query(12, ge=1, le=100),
    db: Session = Depends(get_db),
):
    if min_price is not None and max_price is not None and min_price > max_price:
        raise HTTPException(status_code=400, detail="min_price cannot be more than max_price")

    base = (
        db.query(Product)
        .join(Category)
        .filter(Product.is_active == True)  # noqa: E712
    )
    if search and search.strip():
        like = f"%{search.strip()}%"
        base = base.filter(
            or_(
                Product.name.ilike(like),
                Product.description.ilike(like),
                Product.brand.ilike(like),
            )
        )
    if category:
        base = base.filter(func.lower(Category.name) == category.strip().lower())
    if brand:
        base = base.filter(func.lower(Product.brand) == brand.strip().lower())
    if min_price is not None:
        base = base.filter(Product.price >= min_price)
    if max_price is not None:
        base = base.filter(Product.price <= max_price)
    if min_rating is not None:
        base = base.filter(Product.rating_average >= min_rating)
    if in_stock is True:
        base = base.filter(Product.stock_quantity > 0)
    elif in_stock is False:
        base = base.filter(Product.stock_quantity == 0)

    sort_columns = {
        "newest": Product.created_at,
        "price": Product.price,
        "name": func.lower(Product.name),
        "rating": Product.rating_average,
    }
    column = sort_columns[sort_by]
    ordering = column.asc() if order == "asc" else column.desc()

    total = base.count()
    items = (
        base.options(contains_eager(Product.category))
        .order_by(ordering, Product.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return schemas.ProductPage(
        items=[to_out(p) for p in items],
        total=total,
        page=page,
        page_size=page_size,
    )


# These two must stay ABOVE /products/{product_id}
@app.get("/products/recently-viewed", response_model=List[schemas.ProductOut])
def recently_viewed(
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    products = (
        db.query(Product)
        .join(RecentlyViewed, RecentlyViewed.product_id == Product.id)
        .filter(RecentlyViewed.user_id == user.id, Product.is_active == True)  # noqa: E712
        .order_by(RecentlyViewed.viewed_at.desc())
        .limit(10)
        .all()
    )
    return [to_out(p) for p in products]


@app.get("/products/compare", response_model=List[schemas.ProductOut])
def compare_products(
    ids: str = Query(..., description="Comma separated ids, for example 1,2,3"),
    db: Session = Depends(get_db),
):
    try:
        id_list = [int(x) for x in ids.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(status_code=400, detail="ids must be numbers separated by commas")
    id_list = list(dict.fromkeys(id_list))  # remove repeats, keep order
    if not 2 <= len(id_list) <= 4:
        raise HTTPException(status_code=400, detail="Provide 2 to 4 different product ids")
    products = (
        db.query(Product)
        .filter(Product.id.in_(id_list), Product.is_active == True)  # noqa: E712
        .all()
    )
    if len(products) != len(id_list):
        raise HTTPException(status_code=404, detail="One or more products were not found")
    by_id = {p.id: p for p in products}
    return [to_out(by_id[i]) for i in id_list]


@app.get("/products/{product_id}", response_model=schemas.ProductOut)
def get_product(
    product_id: int,
    db: Session = Depends(get_db),
    user: Optional[CurrentUser] = Depends(get_optional_user),
):
    product = get_active_product(db, product_id)
    if user is not None:
        record = (
            db.query(RecentlyViewed)
            .filter(RecentlyViewed.user_id == user.id, RecentlyViewed.product_id == product_id)
            .first()
        )
        if record:
            record.viewed_at = utcnow()
        else:
            db.add(RecentlyViewed(user_id=user.id, product_id=product_id))
        db.commit()
    return to_out(product)


@app.put("/products/{product_id}", response_model=schemas.ProductOut)
def update_product(
    product_id: int,
    data: schemas.ProductUpdate,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_roles(ADMIN)),
):
    product = get_active_product(db, product_id)
    changes = data.model_dump(exclude_unset=True)
    for field, value in changes.items():
        if value is None and field != "image_url":
            raise HTTPException(status_code=422, detail=f"{field} cannot be empty")
        if field == "category":
            product.category_id = get_or_create_category(db, value).id
        elif field == "specifications":
            product.specifications = json.dumps(value)
        elif isinstance(value, str):
            setattr(product, field, value.strip())
        else:
            setattr(product, field, value)
    db.commit()
    db.refresh(product)
    return to_out(product)


@app.delete("/products/{product_id}", status_code=204)
def delete_product(
    product_id: int,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_roles(ADMIN)),
):
    product = get_active_product(db, product_id)
    product.is_active = False  # soft delete, so old orders can still show this product
    db.commit()
    return Response(status_code=204)


@app.post("/products/bulk-import", response_model=schemas.BulkImportResult)
async def bulk_import(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_roles(ADMIN)),
):
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a .csv file")
    raw = await file.read()
    if len(raw) > MAX_IMPORT_BYTES:
        raise HTTPException(status_code=413, detail="File is too large (max 1 MB)")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be saved as UTF-8")

    reader = csv.DictReader(io.StringIO(text))
    columns = {(c or "").strip().lower() for c in (reader.fieldnames or [])}
    missing = REQUIRED_COLUMNS - columns
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Missing columns: {', '.join(sorted(missing))}",
        )

    created = 0
    skipped = 0
    errors: List[str] = []
    for line_no, raw_row in enumerate(reader, start=2):
        if line_no - 1 > MAX_IMPORT_ROWS:
            errors.append(f"Stopped after {MAX_IMPORT_ROWS} rows")
            break
        row = {
            k.strip().lower(): (v or "").strip()
            for k, v in raw_row.items()
            if k is not None
        }
        try:
            data = schemas.ProductCreate(
                name=row.get("name", ""),
                description=row.get("description", ""),
                category=row.get("category", ""),
                brand=row.get("brand", ""),
                price=float(row.get("price", "")),
                image_url=row.get("image_url") or None,
                specifications=parse_specs(row.get("specifications", "")),
            )
        except ValueError as exc:
            if isinstance(exc, ValidationError):
                first = exc.errors()[0]
                where = ".".join(str(x) for x in first["loc"])
                errors.append(f"Row {line_no}: {where} - {first['msg']}")
            else:
                errors.append(f"Row {line_no}: price must be a number")
            continue

        if product_exists(db, data.name, data.brand):
            skipped += 1
            continue
        category = get_or_create_category(db, data.category)
        db.add(
            Product(
                name=data.name.strip(),
                description=data.description.strip(),
                category_id=category.id,
                brand=data.brand.strip(),
                price=data.price,
                image_url=data.image_url,
                specifications=json.dumps(data.specifications),
            )
        )
        db.flush()
        created += 1

    db.commit()
    return schemas.BulkImportResult(created=created, skipped=skipped, errors=errors)