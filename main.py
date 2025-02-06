from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List
import uuid

app = FastAPI(
    title="API управління кошиком та доставкою",
    description="API для додавання товарів в кошик, розрахунку вартості доставки та управління адресами доставки.",
    version="1.0.0",
)

# ================================
# Моделі даних (Pydantic Models)
# ================================

class Product(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Унікальний ідентифікатор товару")
    name: str = Field(..., description="Назва товару")
    price: float = Field(..., description="Ціна одиниці товару")
    quantity: int = Field(..., description="Кількість одиниць товару")

class Cart(BaseModel):
    user_id: str = Field(..., description="Ідентифікатор користувача")
    items: List[Product] = Field(default_factory=list, description="Список товарів в кошику")
    total: float = Field(0.0, description="Загальна вартість кошика")

class DeliveryAddress(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Унікальний ідентифікатор адреси")
    street: str = Field(..., description="Вулиця")
    city: str = Field(..., description="Місто")
    postal_code: str = Field(..., description="Поштовий індекс")
    country: str = Field(..., description="Країна")

class DeliveryCostRequest(BaseModel):
    address: DeliveryAddress

class DeliveryCostResponse(BaseModel):
    cost: float = Field(..., description="Розрахована вартість доставки")

class DeliveryInfo(BaseModel):
    order_id: str = Field(..., description="Ідентифікатор замовлення")
    user_id: str = Field(..., description="Ідентифікатор користувача")
    delivery_address: DeliveryAddress = Field(..., description="Адреса доставки")
    delivery_cost: float = Field(..., description="Вартість доставки")
    status: str = Field(..., description="Статус доставки (наприклад, Processing, Shipped, Delivered)")

class AvailabilityCheckRequest(BaseModel):
    region: str = Field(..., description="Регіон доставки")
    product_id: str = Field(..., description="Ідентифікатор товару")

class AvailabilityCheckResponse(BaseModel):
    available: bool = Field(..., description="Чи доступний товар для доставки")
    message: str = Field(..., description="Повідомлення з інформацією про доступність")

# ========================================
# Імітація сховища даних (in-memory DB)
# ========================================

carts = {}           # Ключ: user_id, значення: об'єкт Cart
user_addresses = {}  # Ключ: user_id, значення: список DeliveryAddress
deliveries = {}      # Ключ: order_id, значення: об'єкт DeliveryInfo

# ==========================================
# Ендпоінти для управління кошиком (Cart API)
# ==========================================

@app.get("/cart/{user_id}", response_model=Cart, tags=["Кошик"])
def get_cart(user_id: str):
    """
    Отримати інформацію про кошик користувача.
    Якщо кошик не існує, створюється новий порожній кошик.
    """
    if user_id in carts:
        return carts[user_id]
    else:
        cart = Cart(user_id=user_id)
        carts[user_id] = cart
        return cart

@app.post("/cart/{user_id}/items", response_model=Cart, tags=["Кошик"])
def add_product_to_cart(user_id: str, product: Product):
    """
    Додати товар до кошика.
    
    **Приклад запиту (JSON):**
    ```json
    {
      "name": "Ноутбук",
      "price": 1200.99,
      "quantity": 1
    }
    ```
    """
    cart = carts.get(user_id)
    if not cart:
        cart = Cart(user_id=user_id)
        carts[user_id] = cart
    cart.items.append(product)
    cart.total += product.price * product.quantity
    return cart

@app.delete("/cart/{user_id}/items/{product_id}", response_model=Cart, tags=["Кошик"])
def remove_product_from_cart(user_id: str, product_id: str):
    """
    Видалити товар з кошика за ідентифікатором товару.
    """
    cart = carts.get(user_id)
    if not cart:
        raise HTTPException(status_code=404, detail="Кошик не знайдено")
    product_to_remove = None
    for item in cart.items:
        if item.id == product_id:
            product_to_remove = item
            break
    if not product_to_remove:
        raise HTTPException(status_code=404, detail="Товар не знайдено в кошику")
    cart.items.remove(product_to_remove)
    cart.total -= product_to_remove.price * product_to_remove.quantity
    return cart

@app.post("/cart/{user_id}/checkout", response_model=DeliveryInfo, tags=["Кошик", "Доставка"])
def checkout(user_id: str, address: DeliveryAddress):
    """
    Оформлення замовлення:
    
    - Обчислюється вартість доставки (базова вартість + додаткова вартість за кількість товарів)
    - Створюється об'єкт замовлення з інформацією про доставку
    - Кошик очищується після оформлення замовлення
    
    **Приклад запиту (JSON для адреси доставки):**
    ```json
    {
      "street": "Вулиця Шевченка, 10",
      "city": "Київ",
      "postal_code": "01001",
      "country": "Україна"
    }
    ```
    """
    cart = carts.get(user_id)
    if not cart or len(cart.items) == 0:
        raise HTTPException(status_code=400, detail="Кошик порожній")
    
    # Обчислення вартості доставки:
    base_cost = 5.0
    delivery_cost = base_cost + sum(item.quantity * item.price for item in cart.items)
    
    order_id = str(uuid.uuid4())
    delivery_info = DeliveryInfo(
        order_id=order_id,
        user_id=user_id,
        delivery_address=address,
        delivery_cost=delivery_cost,
        status="Processing"
    )
    deliveries[order_id] = delivery_info

    # Очищення кошика після оформлення замовлення
    carts[user_id] = Cart(user_id=user_id)
    
    return delivery_info

# ======================================
# Ендпоінти для управління доставкою
# ======================================

@app.post("/delivery/calculate", response_model=DeliveryCostResponse, tags=["Доставка"])
def calculate_delivery_cost(request: DeliveryCostRequest):
    """
    Обчислення вартості доставки на основі адреси користувача.
    
    **Приклад запиту:**
    ```json
    {
      "address": {
         "street": "Вулиця Грушевського, 15",
         "city": "Львів",
         "postal_code": "79000",
         "country": "Україна"
      }
    }
    ```
    """
    # Проста логіка: для України вартість 5.0, для інших країн – 15.0
    if request.address.country.lower() == "україна":
        cost = 5.0
    else:
        cost = 15.0
    return DeliveryCostResponse(cost=cost)

@app.get("/delivery/info/{order_id}", response_model=DeliveryInfo, tags=["Доставка"])
def get_delivery_info(order_id: str):
    """
    Отримання інформації про доставку за номером замовлення.
    """
    delivery = deliveries.get(order_id)
    if not delivery:
        raise HTTPException(status_code=404, detail="Інформацію про доставку не знайдено")
    return delivery

@app.post("/delivery/availability", response_model=AvailabilityCheckResponse, tags=["Доставка"])
def check_delivery_availability(request: AvailabilityCheckRequest):
    """
    Перевірка доступності товарів для доставки в певний регіон.
    
    **Приклад запиту:**
    ```json
    {
      "region": "Схід",
      "product_id": "abc1231"
    }
    ```
    
    Логіка: для прикладу, якщо регіон "Схід" і ідентифікатор товару закінчується на "1", товар недоступний.
    """
    if request.region.lower() == "схід" and request.product_id.endswith("1"):
        return AvailabilityCheckResponse(available=False, message="Товар недоступний для доставки в даний регіон")
    else:
        return AvailabilityCheckResponse(available=True, message="Товар доступний для доставки")

# =============================================
# Ендпоінти для управління адресами доставки
# =============================================

@app.get("/user/{user_id}/addresses", response_model=List[DeliveryAddress], tags=["Адреса доставки"])
def get_user_addresses(user_id: str):
    """
    Отримання списку адрес доставки користувача.
    """
    return user_addresses.get(user_id, [])

@app.post("/user/{user_id}/addresses", response_model=List[DeliveryAddress], tags=["Адреса доставки"])
def add_delivery_address(user_id: str, address: DeliveryAddress):
    """
    Додавання нової адреси доставки до профілю користувача.
    
    **Приклад запиту:**
    ```json
    {
      "street": "Вулиця Незалежності, 22",
      "city": "Одеса",
      "postal_code": "65000",
      "country": "Україна"
    }
    ```
    """
    addresses = user_addresses.get(user_id, [])
    addresses.append(address)
    user_addresses[user_id] = addresses
    return addresses

# ============================
# Запуск додатку (як standalone)
# ============================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
