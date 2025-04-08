from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
import datetime
import uuid
import databutton as db
import re

router = APIRouter()

# Helper function to sanitize storage keys
def sanitize_storage_key(key: str) -> str:
    """Sanitize storage key to only allow alphanumeric and ._- symbols"""
    return re.sub(r'[^a-zA-Z0-9._-]', '', key)

# Data models
class DeliveryTemplateBase(BaseModel):
    name: str
    content: str
    description: Optional[str] = None
    variables: List[str] = Field(default_factory=list)

class DeliveryTemplate(DeliveryTemplateBase):
    id: str
    created_at: datetime.datetime
    updated_at: datetime.datetime

class CreateTemplateRequest(DeliveryTemplateBase):
    pass

class UpdateTemplateRequest(DeliveryTemplateBase):
    pass

class TemplateListResponse(BaseModel):
    templates: List[DeliveryTemplate]

class TemplateResponse(BaseModel):
    template: DeliveryTemplate

class ProductBase(BaseModel):
    name: str
    description: Optional[str] = None
    price: float = 0.0
    template_id: str
    template_variables: Dict[str, str] = Field(default_factory=dict)
    enable_ai: bool = False

class Product(ProductBase):
    id: str
    created_at: datetime.datetime
    updated_at: datetime.datetime

class CreateProductRequest(ProductBase):
    pass

class UpdateProductRequest(ProductBase):
    pass

class ProductListResponse(BaseModel):
    products: List[Product]

class ProductResponse(BaseModel):
    product: Product

class DeliveryRecord(BaseModel):
    id: str
    product_id: str
    customer_id: str
    customer_email: str
    message_content: str
    status: str
    created_at: datetime.datetime
    template_id: str

class CreateDeliveryRequest(BaseModel):
    product_id: str
    customer_id: str
    customer_email: str
    variables: Optional[Dict[str, str]] = None

class DeliveryResponse(BaseModel):
    delivery: DeliveryRecord

class DeliveryListResponse(BaseModel):
    deliveries: List[DeliveryRecord]

# Storage helper functions
def get_templates() -> List[DeliveryTemplate]:
    try:
        templates_data = db.storage.json.get("delivery_templates", default=[])
        return [DeliveryTemplate(**template) for template in templates_data]
    except Exception as e:
        print(f"Error getting templates: {e}")
        return []

def save_templates(templates: List[DeliveryTemplate]):
    templates_data = [template.dict() for template in templates]
    db.storage.json.put(sanitize_storage_key("delivery_templates"), templates_data)

def get_products() -> List[Product]:
    try:
        products_data = db.storage.json.get("delivery_products", default=[])
        return [Product(**product) for product in products_data]
    except Exception as e:
        print(f"Error getting products: {e}")
        return []

def save_products(products: List[Product]):
    products_data = [product.dict() for product in products]
    db.storage.json.put(sanitize_storage_key("delivery_products"), products_data)

def get_deliveries() -> List[DeliveryRecord]:
    try:
        deliveries_data = db.storage.json.get("delivery_records", default=[])
        return [DeliveryRecord(**delivery) for delivery in deliveries_data]
    except Exception as e:
        print(f"Error getting deliveries: {e}")
        return []

def save_deliveries(deliveries: List[DeliveryRecord]):
    deliveries_data = [delivery.dict() for delivery in deliveries]
    db.storage.json.put(sanitize_storage_key("delivery_records"), deliveries_data)

# API endpoints for delivery templates
@router.get("/templates", response_model=TemplateListResponse)
def get_all_templates():
    templates = get_templates()
    return TemplateListResponse(templates=templates)

@router.post("/templates", response_model=TemplateResponse)
def create_template(request: CreateTemplateRequest):
    templates = get_templates()
    
    # Extract variables from content using regex pattern {{variable_name}}
    variables = re.findall(r'{{([\w_]+)}}', request.content)
    
    new_template = DeliveryTemplate(
        id=str(uuid.uuid4()),
        name=request.name,
        content=request.content,
        description=request.description,
        variables=variables,
        created_at=datetime.datetime.now(),
        updated_at=datetime.datetime.now()
    )
    
    templates.append(new_template)
    save_templates(templates)
    
    return TemplateResponse(template=new_template)

@router.get("/templates/{template_id}", response_model=TemplateResponse)
def get_template(template_id: str):
    templates = get_templates()
    template = next((t for t in templates if t.id == template_id), None)
    
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    
    return TemplateResponse(template=template)

@router.put("/templates/{template_id}", response_model=TemplateResponse)
def update_template(template_id: str, request: UpdateTemplateRequest):
    templates = get_templates()
    template_index = next((i for i, t in enumerate(templates) if t.id == template_id), None)
    
    if template_index is None:
        raise HTTPException(status_code=404, detail="Template not found")
    
    # Extract variables from content using regex pattern {{variable_name}}
    variables = re.findall(r'{{([\w_]+)}}', request.content)
    
    updated_template = DeliveryTemplate(
        id=template_id,
        name=request.name,
        content=request.content,
        description=request.description,
        variables=variables,
        created_at=templates[template_index].created_at,
        updated_at=datetime.datetime.now()
    )
    
    templates[template_index] = updated_template
    save_templates(templates)
    
    return TemplateResponse(template=updated_template)

@router.delete("/templates/{template_id}")
def delete_template(template_id: str):
    templates = get_templates()
    template_index = next((i for i, t in enumerate(templates) if t.id == template_id), None)
    
    if template_index is None:
        raise HTTPException(status_code=404, detail="Template not found")
    
    # Check if template is used by any products
    products = get_products()
    if any(p.template_id == template_id for p in products):
        raise HTTPException(status_code=400, detail="Cannot delete template that is used by products")
    
    templates.pop(template_index)
    save_templates(templates)
    
    return {"message": "Template deleted successfully"}

# API endpoints for products
@router.get("/products", response_model=ProductListResponse)
def get_all_products():
    products = get_products()
    return ProductListResponse(products=products)

@router.post("/products", response_model=ProductResponse)
def create_product(request: CreateProductRequest):
    # Verify template exists
    templates = get_templates()
    template = next((t for t in templates if t.id == request.template_id), None)
    
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    
    # Verify all required variables are provided
    missing_vars = [var for var in template.variables if var not in request.template_variables]
    if missing_vars:
        raise HTTPException(
            status_code=400, 
            detail=f"Missing required template variables: {', '.join(missing_vars)}"
        )
    
    products = get_products()
    
    new_product = Product(
        id=str(uuid.uuid4()),
        name=request.name,
        description=request.description,
        price=request.price,
        template_id=request.template_id,
        template_variables=request.template_variables,
        enable_ai=request.enable_ai,
        created_at=datetime.datetime.now(),
        updated_at=datetime.datetime.now()
    )
    
    products.append(new_product)
    save_products(products)
    
    return ProductResponse(product=new_product)

@router.get("/products/{product_id}", response_model=ProductResponse)
def get_product(product_id: str):
    products = get_products()
    product = next((p for p in products if p.id == product_id), None)
    
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    return ProductResponse(product=product)

@router.put("/products/{product_id}", response_model=ProductResponse)
def update_product(product_id: str, request: UpdateProductRequest):
    # Verify template exists
    templates = get_templates()
    template = next((t for t in templates if t.id == request.template_id), None)
    
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    
    # Verify all required variables are provided
    missing_vars = [var for var in template.variables if var not in request.template_variables]
    if missing_vars:
        raise HTTPException(
            status_code=400, 
            detail=f"Missing required template variables: {', '.join(missing_vars)}"
        )
    
    products = get_products()
    product_index = next((i for i, p in enumerate(products) if p.id == product_id), None)
    
    if product_index is None:
        raise HTTPException(status_code=404, detail="Product not found")
    
    updated_product = Product(
        id=product_id,
        name=request.name,
        description=request.description,
        price=request.price,
        template_id=request.template_id,
        template_variables=request.template_variables,
        enable_ai=request.enable_ai,
        created_at=products[product_index].created_at,
        updated_at=datetime.datetime.now()
    )
    
    products[product_index] = updated_product
    save_products(products)
    
    return ProductResponse(product=updated_product)

@router.delete("/products/{product_id}")
def delete_product(product_id: str):
    products = get_products()
    product_index = next((i for i, p in enumerate(products) if p.id == product_id), None)
    
    if product_index is None:
        raise HTTPException(status_code=404, detail="Product not found")
    
    products.pop(product_index)
    save_products(products)
    
    return {"message": "Product deleted successfully"}

# API endpoints for deliveries
@router.get("/deliveries", response_model=DeliveryListResponse)
def get_all_deliveries():
    deliveries = get_deliveries()
    return DeliveryListResponse(deliveries=deliveries)

@router.post("/deliveries", response_model=DeliveryResponse)
def create_delivery(request: CreateDeliveryRequest):
    # Verify product exists
    products = get_products()
    product = next((p for p in products if p.id == request.product_id), None)
    
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    # Get template
    templates = get_templates()
    template = next((t for t in templates if t.id == product.template_id), None)
    
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    
    # Combine product variables with request variables
    variables = {**product.template_variables}
    if request.variables:
        variables.update(request.variables)
    
    # Generate message content by replacing variables in template
    message_content = template.content
    for var_name, var_value in variables.items():
        message_content = message_content.replace('{{' + var_name + '}}', var_value)
    
    deliveries = get_deliveries()
    
    new_delivery = DeliveryRecord(
        id=str(uuid.uuid4()),
        product_id=request.product_id,
        customer_id=request.customer_id,
        customer_email=request.customer_email,
        message_content=message_content,
        status="completed",
        created_at=datetime.datetime.now(),
        template_id=template.id
    )
    
    deliveries.append(new_delivery)
    save_deliveries(deliveries)
    
    # TODO: Add email sending functionality
    # db.notify.email(
    #     to=request.customer_email,
    #     subject=f"Your Digital Product: {product.name}",
    #     content_html=message_content,
    #     content_text=message_content.replace('<br>', '\n')
    # )
    
    return DeliveryResponse(delivery=new_delivery)

@router.get("/deliveries/{delivery_id}", response_model=DeliveryResponse)
def get_delivery(delivery_id: str):
    deliveries = get_deliveries()
    delivery = next((d for d in deliveries if d.id == delivery_id), None)
    
    if not delivery:
        raise HTTPException(status_code=404, detail="Delivery not found")
    
    return DeliveryResponse(delivery=delivery)
