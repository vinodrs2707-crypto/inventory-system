from services.auth_service.app import models
from services.auth_service.app.database import Base, SessionLocal, engine
from services.auth_service.app.security import hash_password

Base.metadata.create_all(bind=engine)

USERS = [
    ("admin@example.com", "Admin User", "Admin@12345", "administrator"),
    ("inventory@example.com", "Inventory Manager", "Inventory@12345", "inventory_manager"),
]

db = SessionLocal()
for email, name, password, role in USERS:
    if db.query(models.User).filter(models.User.email == email).first():
        print(f"Skipped (already exists): {email}")
        continue
    db.add(
        models.User(
            email=email,
            full_name=name,
            hashed_password=hash_password(password),
            role=role,
        )
    )
    print(f"Created {role}: {email}")
db.commit()
db.close()