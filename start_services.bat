@echo off
start "Auth 8001" cmd /k "venv\Scripts\activate && uvicorn services.auth_service.app.main:app --reload --port 8001"
start "Product 8002" cmd /k "venv\Scripts\activate && uvicorn services.product_service.app.main:app --reload --port 8002"
start "Inventory 8003" cmd /k "venv\Scripts\activate && uvicorn services.inventory_service.app.main:app --reload --port 8003"
start "Coupon 8004" cmd /k "venv\Scripts\activate && uvicorn services.coupon_service.app.main:app --reload --port 8004"
start "Cart 8005" cmd /k "venv\Scripts\activate && uvicorn services.cart_service.app.main:app --reload --port 8005"
start "Order 8006" cmd /k "venv\Scripts\activate && uvicorn services.order_service.app.main:app --reload --port 8006"